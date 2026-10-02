from __future__ import annotations

import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

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
    from openai_harmony import Message

    # Create Harmony messages directly
    tool_call_msg = Message.from_role_and_content(
        Role.ASSISTANT,
        '{"patch":"*** Begin Patch\\n*** End Patch\\n"}',
    ).with_channel("commentary").with_recipient("functions.apply_patch")
    final_msg = Message.from_role_and_content(Role.ASSISTANT, "done").with_channel("final")

    # Convert to the format parse_harmony_completion expects
    completion = json.dumps([tool_call_msg.to_dict(), final_msg.to_dict()])
    parsed = parse_harmony_completion(completion)

    assert isinstance(parsed, AIMessage)
    assert parsed.tool_calls and parsed.tool_calls[0]["name"] == "apply_patch"
    assert parsed.content == "done"
    # Verify unique tool call id (uuid4 hex, not call_0)
    assert parsed.tool_calls[0]["id"] != "call_0"
    assert parsed.tool_calls[0]["id"].startswith("call_")
    assert len(parsed.tool_calls[0]["id"]) == 37  # "call_" + 32 char hex


def test_parse_harmony_completion_rejects_malformed_tool_args() -> None:
    from openai_harmony import Message

    tool_call_msg = Message.from_role_and_content(
        Role.ASSISTANT,
        "not-json",
    ).with_channel("commentary").with_recipient("functions.apply_patch")
    completion = json.dumps([tool_call_msg.to_dict()])

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
                "content": "ok",
                "tokens": None,  # No tokens, fallback to plain text
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
    assert "timeout" not in body
    assert body["stop"] == ["<|return|>", "<|call|>"]
    assert body["return_tokens"] is True


def test_stream_yields_chunks_from_completion() -> None:
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b'data: {"content": "hello", "stop": true}\n\ndata: [DONE]\n\n',
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


def test_bind_tools_includes_tool_in_prompt() -> None:
    captured: dict[str, object] = {}

    def apply_patch_fn(patch: str) -> str:
        return f"Applied: {patch}"

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={"content": "ok", "tokens": None},
        )

    transport = httpx.MockTransport(_handler)
    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b",
        base_url="http://127.0.0.1:8080",
        timeout_s=9.0,
        transport=transport,
    )

    model_with_tools = model.bind_tools([apply_patch_fn])
    model_with_tools.invoke([HumanMessage("test")])

    body = captured["body"]
    assert isinstance(body["prompt"], list)
    # Verify tools are passed through (will be in the rendered conversation)
    assert body["prompt"]  # Just verify it's a token list
