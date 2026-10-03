"""Failing-first tests for real SSE streaming in _stream (PR review §4)."""

from __future__ import annotations

import json

import pytest

import httpx
from langchain_core.messages import HumanMessage

from dcode_harmony.providers.harmony import HarmonyCompletionChatModel
from openai_harmony import HarmonyEncodingName, load_harmony_encoding

_ENCODING = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)


def _sse(lines: list[dict]) -> bytes:
    return b"".join(
        b"data: " + json.dumps(line).encode() + b"\n\n" for line in lines
    ) + b"data: [DONE]\n\n"


def _model(handler) -> HarmonyCompletionChatModel:
    return HarmonyCompletionChatModel(
        model="gpt-oss-20b",
        base_url="http://127.0.0.1:8080",
        timeout_s=9.0,
        transport=httpx.MockTransport(handler),
    )


def test_stream_sends_stream_true_and_yields_incremental_chunks() -> None:
    captured: dict[str, object] = {}
    tokens = _ENCODING.encode(
        "<|channel|>final<|message|>hello world<|return|>",
        allowed_special="all",
    )
    half = len(tokens) // 2

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(
                [
                    {"content": "hello ", "tokens": tokens[:half], "stop": False},
                    {"content": "world", "tokens": tokens[half:], "stop": True},
                ]
            ),
        )

    chunks = list(_model(handler).stream([HumanMessage("hi")]))
    assert captured["body"].get("stream") is True
    texts = [chunk.content for chunk in chunks if isinstance(chunk.content, str)]
    assert "".join(texts) == "hello world"
    assert len(chunks) >= 2  # incremental, not one replayed chunk


def test_stream_hides_analysis_channel_from_output() -> None:
    tokens = _ENCODING.encode(
        "<|channel|>analysis<|message|>secret reasoning"
        "<|end|><|start|>assistant<|channel|>final<|message|>visible<|return|>",
        allowed_special="all",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse([{"content": "secret reasoning\nvisible", "tokens": tokens, "stop": True}]),
        )

    chunks = list(_model(handler).stream([HumanMessage("hi")]))
    text = "".join(c.content for c in chunks if isinstance(c.content, str))
    assert "visible" in text
    assert "secret reasoning" not in text


def test_stream_emits_tool_call_chunk() -> None:
    tokens = _ENCODING.encode(
        'to=functions.apply_patch<|channel|>commentary json'
        '<|message|>{"patch": "x"}<|call|>',
        allowed_special="all",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse([{"content": '{"patch": "x"}', "tokens": tokens, "stop": True}]),
        )

    chunks = list(_model(handler).stream([HumanMessage("hi")]))
    tool_calls = []
    for c in chunks:
        tool_calls.extend(getattr(c, "tool_calls", []) or [])
    assert tool_calls and tool_calls[0]["name"] == "apply_patch"
    assert tool_calls[0]["args"] == {"patch": "x"}


def test_stream_http_error_propagates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(httpx.HTTPStatusError):
        list(_model(handler).stream([HumanMessage("hi")]))




def _sse_tokens(token_groups: list[list[int]]) -> bytes:
    lines = []
    for group in token_groups:
        lines.append(
            {"content": "", "tokens": group, "stop": False}
        )
    lines.append({"content": "", "tokens": [], "stop": True})
    return b"".join(b"data: " + json.dumps(l).encode() + b"\n\n" for l in lines)


def _run_stream_tokens(token_groups: list[list[int]]):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_tokens(token_groups),
        )

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b",
        base_url="http://127.0.0.1:8080",
        transport=httpx.MockTransport(handler),
    )
    return list(model.stream([HumanMessage("hi")]))


def test_tool_calls_in_same_event_are_both_emitted() -> None:
    enc = _ENCODING
    call1 = enc.encode(
        'to=functions.apply_patch<|channel|>commentary json<|message|>{"patch": "a"}<|call|>',
        allowed_special="all",
    )
    call2 = enc.encode(
        '<|start|>assistant to=functions.apply_patch<|channel|>commentary json<|message|>{"patch": "b"}<|call|>',
        allowed_special="all",
    )
    chunks = _run_stream_tokens([call1 + call2])  # single event with both
    tool_calls = [tc for c in chunks for tc in (c.tool_calls or [])]
    assert len(tool_calls) == 2
    assert {tc["args"]["patch"] for tc in tool_calls} == {"a", "b"}
    assert tool_calls[0]["id"] != tool_calls[1]["id"]


def test_fragmented_tool_call_across_events_emitted_once() -> None:
    enc = _ENCODING
    tokens = enc.encode(
        'to=functions.apply_patch<|channel|>commentary json<|message|>{"patch": "x"}<|call|>',
        allowed_special="all",
    )
    third = len(tokens) // 3
    chunks = _run_stream_tokens([tokens[:third], tokens[third : 2 * third], tokens[2 * third :]])
    tool_calls = [tc for c in chunks for tc in (c.tool_calls or [])]
    assert len(tool_calls) == 1
    assert tool_calls[0]["args"] == {"patch": "x"}


def test_message_split_across_events_yields_full_text() -> None:
    enc = _ENCODING
    tokens = enc.encode("<|channel|>final<|message|>hello there world<|return|>", allowed_special="all")
    half = len(tokens) // 2
    chunks = _run_stream_tokens([tokens[:half], tokens[half:]])
    text = "".join(c.content for c in chunks if isinstance(c.content, str))
    assert text == "hello there world"


def test_text_without_tokens_does_not_leak_harmony_markup() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b'data: {"content": "<|channel|>analysis<|message|>secret"}\n\ndata: {"content": "done", "stop": true}\n\n',
        )

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b",
        base_url="http://127.0.0.1:8080",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ValueError, match="Harmony markup"):
        list(model.stream([HumanMessage("hi")]))
