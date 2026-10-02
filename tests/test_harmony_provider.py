from __future__ import annotations

import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from dcode_harmony.providers.harmony import (
    HarmonyCompletionChatModel,
    build_harmony_conversation,
    parse_harmony_completion,
)
from openai_harmony import HarmonyEncodingName, load_harmony_encoding, Role


def test_build_harmony_conversation_includes_system_and_tools() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "apply_patch",
                "description": "Apply a patch",
                "parameters": {"type": "object"},
            },
        }
    ]
    conversation = build_harmony_conversation(
        [SystemMessage("rules"), HumanMessage("oi")],
        tools=tools,
    )
    payload = conversation.to_dict()
    assert payload["messages"][0]["role"] == "developer"
    assert payload["messages"][0]["content"][0]["type"] == "developer_content"
    assert payload["messages"][1]["role"] == "system"
    assert payload["messages"][2]["role"] == "user"


def test_payload_uses_native_harmony_tokens() -> None:
    encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={"content": "", "tokens": []},
        )

    transport = httpx.MockTransport(_handler)
    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b",
        base_url="http://127.0.0.1:8080",
        timeout_s=9.0,
        transport=transport,
    )

    model.invoke([SystemMessage("Be helpful"), HumanMessage("Hello")])

    body = captured["body"]
    assert isinstance(body["prompt"], list)
    assert isinstance(body["prompt"][0], int)
    assert body["return_tokens"] is True
    assert "timeout" not in body

    # Verify prompt ends with assistant generation prefix
    assistant_prefix_tokens = encoding.render_conversation_for_completion(
        build_harmony_conversation([SystemMessage("Be helpful"), HumanMessage("Hello")]),
        Role.ASSISTANT,
    )
    assert body["prompt"] == assistant_prefix_tokens


def test_parse_harmony_completion_maps_tool_call() -> None:
    completion = json.dumps(
        [
            {
                "role": "assistant",
                "channel": "commentary",
                "recipient": "functions.apply_patch",
                "content": '{"patch":"*** Begin Patch\\n*** End Patch\\n"}',
            },
            {"role": "assistant", "channel": "final", "content": "done"},
        ]
    )
    message = parse_harmony_completion(completion)
    assert isinstance(message, AIMessage)
    assert message.tool_calls and message.tool_calls[0]["name"] == "apply_patch"
    assert message.content == "done"


def test_parse_harmony_completion_rejects_malformed_tool_args() -> None:
    completion = json.dumps(
        [
            {
                "role": "assistant",
                "channel": "commentary",
                "recipient": "functions.apply_patch",
                "content": "not-json",
            }
        ]
    )
    with pytest.raises(ValueError, match="Malformed tool-call"):
        parse_harmony_completion(completion)


def test_completion_http_contract() -> None:
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "content": '[{"role":"assistant","channel":"final","content":"ok"}]',
            },
        )

    transport = httpx.MockTransport(_handler)
    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b",
        base_url="http://127.0.0.1:8080",
        timeout_s=9.0,
        transport=transport,
    )

    result = model.invoke([HumanMessage("hello")])
    assert result.content == "ok"
    assert captured["url"] == "http://127.0.0.1:8080/completion"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["timeout"] == 9.0
    assert body["stop"] == ["<|return|>", "<|call|>"]


def test_stream_yields_chunks_from_completion() -> None:
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "content": '[{"role":"assistant","channel":"final","content":"hello"}]',
            },
        )

    transport = httpx.MockTransport(_handler)
    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b",
        base_url="http://127.0.0.1:8080",
        timeout_s=9.0,
        transport=transport,
    )

    chunks = list(model.stream([HumanMessage("test")]))
    assert len(chunks) >= 1
    assert chunks[0].content == "hello"
    assert captured["url"] == "http://127.0.0.1:8080/completion"
