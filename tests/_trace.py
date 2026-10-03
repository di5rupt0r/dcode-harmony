"""Execution-trace harness for provider runs.

Provides TracingTransport (an httpx.BaseTransport wrapper that records every
request/response pair) and trace_event() for test-side annotations.

All records are JSONL with these fields:
  ts, test, phase, url, prompt_tokens, stream, n_predict, max_tokens,
  ttft_s, total_s, tokens_predicted, stop, content_preview, error
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

_CONTENT_PREVIEW_MAX = 120


def get_trace_dir() -> Path | None:
    """Return the trace directory from DCODE_TRACE_DIR, or None if unset."""
    env_dir = os.environ.get("DCODE_TRACE_DIR")
    return Path(env_dir) if env_dir else None


def _safe_json(body: bytes) -> dict[str, Any]:
    """Parse JSON body, returning empty dict on failure."""
    try:
        data = json.loads(body)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


class _TracingResponse:
    """Wraps an httpx.Response to record SSE events during streaming."""

    def __init__(
        self, response: httpx.Response, transport: TracingTransport, url: str
    ) -> None:
        self._response = response
        self._transport = transport
        self._url = url
        self._start_time = time.monotonic()
        self._first_token_time: float | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._response, name)

    def iter_bytes(self, chunk_size: int | None = None) -> Any:
        """Intercept iter_bytes to record SSE events."""
        for chunk in self._response.iter_bytes(chunk_size=chunk_size):
            self._record_sse_event(chunk)
            yield chunk

    def _record_sse_event(self, chunk: bytes) -> None:
        """Record an SSE event from a chunk of data."""
        if self._first_token_time is None:
            self._first_token_time = time.monotonic()

        text = chunk.decode("utf-8", errors="replace")
        for line in text.split("\n"):
            if line.startswith("data:"):
                data = line[5:].strip()
                if data and data != "[DONE]":
                    try:
                        event = json.loads(data)
                        ttft = None
                        if self._first_token_time is not None:
                            ttft = self._first_token_time - self._start_time
                        self._transport.records.append({
                            "ts": time.monotonic() - self._transport._start_time,
                            "test": self._transport._test_name,
                            "phase": "sse",
                            "url": self._url,
                            "ttft_s": ttft,
                            "content": event.get("content", ""),
                            "tokens": event.get("tokens", []),
                        })
                    except json.JSONDecodeError:
                        pass


class TracingTransport(httpx.BaseTransport):
    """Wraps an httpx.BaseTransport and records request/response pairs.

    Records are stored in self.records as a list of dicts. Each record has
    at minimum: ts, test, phase, url. Additional fields depend on phase.
    """

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner
        self.records: list[dict[str, Any]] = []
        self._test_name: str = ""
        self._start_time: float = 0.0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Handle a request, recording request/response/error."""
        if self._start_time == 0.0:
            self._start_time = time.monotonic()

        url = str(request.url)
        body = _safe_json(request.content) if request.content else {}
        is_stream = bool(body.get("stream"))

        # Record request
        req_record: dict[str, Any] = {
            "ts": time.monotonic() - self._start_time,
            "test": self._test_name,
            "phase": "request",
            "url": url,
            "prompt_tokens": len(body.get("prompt", [])) if isinstance(body.get("prompt"), list) else None,
            "stream": body.get("stream"),
            "n_predict": body.get("n_predict"),
            "max_tokens": body.get("n_predict"),
        }
        self.records.append(req_record)

        try:
            response = self._inner.handle_request(request)
        except Exception as exc:
            # Record error
            self.records.append({
                "ts": time.monotonic() - self._start_time,
                "test": self._test_name,
                "phase": "error",
                "url": url,
                "error": f"{type(exc).__name__}: {exc}",
            })
            raise

        # For streaming responses, wrap to record SSE events
        if is_stream:
            return _TracingResponse(response, self, url)  # type: ignore[return-value]

        # Record response (non-streaming)
        resp_body = _safe_json(response.content) if response.content else {}
        resp_record: dict[str, Any] = {
            "ts": time.monotonic() - self._start_time,
            "test": self._test_name,
            "phase": "response",
            "url": url,
            "total_s": time.monotonic() - self._start_time - req_record["ts"],
            "tokens_predicted": len(resp_body.get("tokens", [])) if isinstance(resp_body.get("tokens"), list) else None,
            "stop": resp_body.get("stop"),
            "content_preview": str(resp_body.get("content", ""))[:_CONTENT_PREVIEW_MAX],
        }
        self.records.append(resp_record)

        return response

    def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Async requests are not supported by the trace harness."""
        raise NotImplementedError("TracingTransport does not support async requests")


def trace_event(
    path: str | Path,
    phase: str,
    test: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Write a single trace event as JSONL to the given file.

    Args:
        path: Path to the JSONL trace file.
        phase: Event phase (e.g. "render", "tool", "error").
        test: Test node id.
        data: Additional fields to include in the record.
    """
    record: dict[str, Any] = {
        "ts": time.monotonic(),
        "test": test,
        "phase": phase,
    }
    if data:
        record.update(data)

    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with path_obj.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
