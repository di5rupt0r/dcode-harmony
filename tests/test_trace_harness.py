"""Unit tests for the execution-trace harness (tests/_trace.py + conftest.py).

These tests do NOT require a real llama-server. They verify the trace record
schema, the TracingTransport wrapper, the failure hook, and the zero-overhead
default behavior.
"""

from __future__ import annotations

import json
import os

import httpx
import pytest

from tests._trace import TracingTransport, trace_event


# ---------------------------------------------------------------------------
# TracingTransport — request/response recording
# ---------------------------------------------------------------------------


def test_tracing_transport_records_request_and_response() -> None:
    """A non-streaming request produces request + response records."""
    inner = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"content": "ok", "tokens": None})
    )
    transport = TracingTransport(inner)
    request = httpx.Request("POST", "http://test/completion", json={"prompt": [1]})
    response = transport.handle_request(request)

    assert response.status_code == 200
    records = transport.records
    assert len(records) == 2
    assert records[0]["phase"] == "request"
    assert records[1]["phase"] == "response"
    assert records[0]["url"] == "http://test/completion"
    assert records[1]["url"] == "http://test/completion"


def test_tracing_transport_captures_prompt_tokens() -> None:
    """The request record includes prompt_tokens (length of token array)."""
    inner = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"content": "", "tokens": []})
    )
    transport = TracingTransport(inner)
    request = httpx.Request(
        "POST", "http://test/completion", json={"prompt": [1, 2, 3]}
    )
    transport.handle_request(request)

    req_record = transport.records[0]
    assert req_record["prompt_tokens"] == 3


def test_tracing_transport_captures_stream_flag() -> None:
    """The request record includes the stream flag."""
    inner = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"content": "", "tokens": []})
    )
    transport = TracingTransport(inner)
    request = httpx.Request(
        "POST", "http://test/completion", json={"prompt": [1], "stream": True}
    )
    transport.handle_request(request)

    req_record = transport.records[0]
    assert req_record["stream"] is True


def test_tracing_transport_captures_n_predict() -> None:
    """The request record includes n_predict."""
    inner = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"content": "", "tokens": []})
    )
    transport = TracingTransport(inner)
    request = httpx.Request(
        "POST", "http://test/completion", json={"prompt": [1], "n_predict": 512}
    )
    transport.handle_request(request)

    req_record = transport.records[0]
    assert req_record["n_predict"] == 512


def test_tracing_transport_captures_max_tokens_from_model() -> None:
    """max_tokens is derived from n_predict in the payload."""
    inner = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"content": "", "tokens": []})
    )
    transport = TracingTransport(inner)
    request = httpx.Request(
        "POST", "http://test/completion", json={"prompt": [1], "n_predict": 2048}
    )
    transport.handle_request(request)

    req_record = transport.records[0]
    assert req_record["max_tokens"] == 2048


def test_tracing_transport_records_error() -> None:
    """An exception during handle_request produces an error record."""

    class FailingTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

    transport = TracingTransport(FailingTransport())
    request = httpx.Request("POST", "http://test/completion", json={"prompt": [1]})
    with pytest.raises(httpx.ConnectError):
        transport.handle_request(request)

    records = transport.records
    assert any(r["phase"] == "error" for r in records)
    error_record = next(r for r in records if r["phase"] == "error")
    assert "ConnectError" in error_record["error"]


def test_tracing_transport_records_total_s() -> None:
    """The response record includes total_s (wall time)."""
    inner = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"content": "ok", "tokens": None})
    )
    transport = TracingTransport(inner)
    request = httpx.Request("POST", "http://test/completion", json={"prompt": [1]})
    transport.handle_request(request)

    resp_record = transport.records[1]
    assert "total_s" in resp_record
    assert isinstance(resp_record["total_s"], float)
    assert resp_record["total_s"] >= 0.0


def test_tracing_transport_records_content_preview() -> None:
    """The response record includes a content_preview."""
    inner = httpx.MockTransport(
        lambda req: httpx.Response(
            200, json={"content": "hello world", "tokens": None}
        )
    )
    transport = TracingTransport(inner)
    request = httpx.Request("POST", "http://test/completion", json={"prompt": [1]})
    transport.handle_request(request)

    resp_record = transport.records[1]
    assert "content_preview" in resp_record
    assert "hello world" in resp_record["content_preview"]


def test_tracing_transport_records_tokens_predicted() -> None:
    """The response record includes tokens_predicted from the response body."""
    inner = httpx.MockTransport(
        lambda req: httpx.Response(
            200, json={"content": "ok", "tokens": [1, 2, 3]}
        )
    )
    transport = TracingTransport(inner)
    request = httpx.Request("POST", "http://test/completion", json={"prompt": [1]})
    transport.handle_request(request)

    resp_record = transport.records[1]
    assert resp_record["tokens_predicted"] == 3


def test_tracing_transport_records_stop() -> None:
    """The response record includes stop from the response body."""
    inner = httpx.MockTransport(
        lambda req: httpx.Response(
            200, json={"content": "ok", "tokens": [1], "stop": True}
        )
    )
    transport = TracingTransport(inner)
    request = httpx.Request("POST", "http://test/completion", json={"prompt": [1]})
    transport.handle_request(request)

    resp_record = transport.records[1]
    assert resp_record["stop"] is True


# ---------------------------------------------------------------------------
# TracingTransport — streaming
# ---------------------------------------------------------------------------


def test_tracing_transport_streaming_records_sse_events() -> None:
    """A streaming response produces sse phase records with ttft_s."""
    sse_body = (
        b'data: {"content": "hello", "tokens": [10]}\n\n'
        b'data: {"content": " world", "tokens": [11]}\n\n'
    )

    def _handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse_body,
        )

    transport = TracingTransport(httpx.MockTransport(_handler))
    request = httpx.Request(
        "POST", "http://test/completion", json={"prompt": [1], "stream": True}
    )
    response = transport.handle_request(request)

    # Consume the stream
    body = b""
    for chunk in response.iter_bytes():
        body += chunk

    assert b"hello" in body
    records = transport.records
    sse_records = [r for r in records if r["phase"] == "sse"]
    assert len(sse_records) >= 2
    # First SSE event should have ttft_s
    assert "ttft_s" in sse_records[0]
    assert isinstance(sse_records[0]["ttft_s"], float)


# ---------------------------------------------------------------------------
# trace_event helper
# ---------------------------------------------------------------------------


def test_trace_event_writes_valid_jsonl(tmp_path) -> None:
    """trace_event writes a JSON object per line to the given file."""
    trace_file = tmp_path / "test.jsonl"
    trace_event(
        str(trace_file),
        phase="render",
        test="test_something",
        data={"prompt_tokens": 42},
    )
    trace_event(
        str(trace_file),
        phase="tool",
        test="test_something",
        data={"tool_name": "apply_patch"},
    )

    lines = trace_file.read_text().strip().split("\n")
    assert len(lines) == 2
    rec0 = json.loads(lines[0])
    rec1 = json.loads(lines[1])
    assert rec0["phase"] == "render"
    assert rec0["test"] == "test_something"
    assert rec0["prompt_tokens"] == 42
    assert rec1["phase"] == "tool"
    assert rec1["tool_name"] == "apply_patch"


def test_trace_event_includes_ts(tmp_path) -> None:
    """trace_event includes a monotonic ts field."""
    trace_file = tmp_path / "test.jsonl"
    trace_event(str(trace_file), phase="render", test="t", data={})
    rec = json.loads(trace_file.read_text().strip())
    assert "ts" in rec
    assert isinstance(rec["ts"], float)


# ---------------------------------------------------------------------------
# conftest.py — zero-overhead default
# ---------------------------------------------------------------------------


def test_no_trace_dir_env_var_means_no_files(
    tmp_path, monkeypatch
) -> None:
    """When DCODE_TRACE_DIR is unset, no trace files are created."""
    monkeypatch.delenv("DCODE_TRACE_DIR", raising=False)
    from tests._trace import get_trace_dir

    result = get_trace_dir()
    assert result is None


def test_trace_dir_env_var_sets_trace_dir(
    tmp_path, monkeypatch
) -> None:
    """When DCODE_TRACE_DIR is set, get_trace_dir returns that path."""
    monkeypatch.setenv("DCODE_TRACE_DIR", str(tmp_path))
    from tests._trace import get_trace_dir

    result = get_trace_dir()
    assert result is not None
    assert str(result) == str(tmp_path)


# ---------------------------------------------------------------------------
# conftest.py — failure hook
# ---------------------------------------------------------------------------


def test_failure_hook_exists() -> None:
    """The pytest_runtest_makereport hook is defined in conftest."""
    from tests.conftest import pytest_runtest_makereport

    assert callable(pytest_runtest_makereport)


# ---------------------------------------------------------------------------
# TracingTransport — integration with HarmonyCompletionChatModel
# ---------------------------------------------------------------------------


def test_provider_with_tracing_transport_records() -> None:
    """HarmonyCompletionChatModel with TracingTransport produces records."""
    from langchain_core.messages import HumanMessage

    from dcode_harmony.providers.harmony import HarmonyCompletionChatModel

    inner = httpx.MockTransport(
        lambda req: httpx.Response(
            200, json={"content": "ok", "tokens": None}
        )
    )
    transport = TracingTransport(inner)
    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b",
        base_url="http://127.0.0.1:8080",
        timeout_s=9.0,
        transport=transport,
    )
    model.invoke([HumanMessage("hello")])

    records = transport.records
    assert len(records) >= 2
    assert records[0]["phase"] == "request"
    assert records[1]["phase"] == "response"
    assert records[0]["url"] == "http://127.0.0.1:8080/completion"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_record_schema_fields_present() -> None:
    """All expected schema fields are present in request/response records."""
    inner = httpx.MockTransport(
        lambda req: httpx.Response(
            200, json={"content": "ok", "tokens": [1], "stop": True}
        )
    )
    transport = TracingTransport(inner)
    request = httpx.Request(
        "POST", "http://test/completion", json={"prompt": [1], "n_predict": 100}
    )
    transport.handle_request(request)

    req_record = transport.records[0]
    expected_req_fields = {"ts", "test", "phase", "url", "prompt_tokens", "stream", "n_predict", "max_tokens"}
    assert expected_req_fields.issubset(req_record.keys())

    resp_record = transport.records[1]
    expected_resp_fields = {"ts", "test", "phase", "url", "total_s", "tokens_predicted", "stop", "content_preview"}
    assert expected_resp_fields.issubset(resp_record.keys())
