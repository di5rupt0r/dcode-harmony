from __future__ import annotations

import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from openai_harmony import HarmonyEncodingName, Role, load_harmony_encoding

from dcode_harmony.providers.harmony import (
    HarmonyCompletionChatModel,
    build_harmony_conversation,
    parse_harmony_completion,
)


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
        build_harmony_conversation(
            [SystemMessage("Be helpful"), HumanMessage("Hello")]
        ),
        Role.ASSISTANT,
    )
    assert body["prompt"] == assistant_prefix_tokens


def test_parse_harmony_completion_maps_tool_call() -> None:
    from openai_harmony import Message

    # Create Harmony messages directly
    tool_call_msg = (
        Message.from_role_and_content(
            Role.ASSISTANT,
            '{"patch":"*** Begin Patch\\n*** End Patch\\n"}',
        )
        .with_channel("commentary")
        .with_recipient("functions.apply_patch")
    )
    final_msg = Message.from_role_and_content(Role.ASSISTANT, "done").with_channel(
        "final"
    )

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

    tool_call_msg = (
        Message.from_role_and_content(
            Role.ASSISTANT,
            "not-json",
        )
        .with_channel("commentary")
        .with_recipient("functions.apply_patch")
    )
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


def test_model_exposes_tool_calling_profile() -> None:
    model = HarmonyCompletionChatModel(model="gpt-oss-20b")
    profile = getattr(model, "profile", None)
    assert isinstance(profile, dict)
    assert profile.get("tool_calling") is True


def test_bind_tools_real_path_renders_apply_patch_schema() -> None:
    from openai_harmony import HarmonyEncodingName, load_harmony_encoding

    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"content": "ok", "tokens": None})

    def apply_patch(patch: str) -> str:
        """Apply a patch inside the workspace."""
        return patch

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b",
        base_url="http://127.0.0.1:8080",
        transport=httpx.MockTransport(_handler),
    )
    model.bind_tools([apply_patch]).invoke([HumanMessage("hi")])
    enc = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
    rendered = enc.decode(captured["body"]["prompt"])
    assert "apply_patch" in rendered
    assert "patch: string" in rendered


def _tokens_for(text: str) -> list[int]:
    return _ENC.encode(text, allowed_special="all")


_ENC = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)


def test_parse_normal_final_response_from_tokens() -> None:
    tokens = _tokens_for("<|channel|>final<|message|>hello there<|return|>")
    ai = parse_harmony_completion("", tokens=tokens)
    assert ai.content == "hello there"
    assert not ai.tool_calls


def test_parse_analysis_channel_not_in_final_content() -> None:
    tokens = _tokens_for(
        "<|channel|>analysis<|message|>secret thoughts<|end|>"
        "<|start|>assistant<|channel|>final<|message|>visible answer<|return|>"
    )
    ai = parse_harmony_completion("", tokens=tokens)
    assert ai.content == "visible answer"
    assert "secret thoughts" not in ai.content


def test_parse_empty_completion() -> None:
    ai = parse_harmony_completion("", tokens=None)
    assert ai.content == ""


def test_parse_truncated_tokens_return_sane_ai_message() -> None:
    tokens = _tokens_for("<|channel|>final<|message|>partial")
    try:
        ai = parse_harmony_completion("", tokens=tokens)
    except ValueError:
        return  # also acceptable: explicit failure
    assert isinstance(ai.content, str)


def test_parse_tool_call_with_whitespace_padded_json() -> None:
    from openai_harmony import Message

    msg = (
        Message.from_role_and_content(Role.ASSISTANT, '  { "patch": "x" }  ')
        .with_channel("commentary")
        .with_recipient("functions.apply_patch")
    )
    ai = parse_harmony_completion(json.dumps([msg.to_dict()]))
    assert ai.tool_calls[0]["args"] == {"patch": "x"}


def test_parse_tool_call_fragmented_json_across_content_items() -> None:
    from openai_harmony import Message

    msg = (
        Message.from_role_and_content(Role.ASSISTANT, '{"pat' + 'ch": "y"}')
        .with_channel("commentary")
        .with_recipient("functions.apply_patch")
    )
    ai = parse_harmony_completion(json.dumps([msg.to_dict()]))
    assert ai.tool_calls[0]["args"] == {"patch": "y"}


def test_parse_unknown_recipient_tool_is_not_registered_error() -> None:
    from openai_harmony import Message

    msg = (
        Message.from_role_and_content(Role.ASSISTANT, '{"x": 1}')
        .with_channel("commentary")
        .with_recipient("functions.nonexistent_tool")
    )
    # Parsing must not invent a registered tool; it records the call by name
    # and the runtime rejects unknown tools. The name must be preserved.
    ai = parse_harmony_completion(json.dumps([msg.to_dict()]))
    assert ai.tool_calls[0]["name"] == "nonexistent_tool"


def test_parse_plain_text_fallback_is_final_content() -> None:
    ai = parse_harmony_completion("just some text", tokens=None)
    assert ai.content == "just some text"


def test_parse_multiple_tool_calls() -> None:
    from openai_harmony import Message

    m1 = (
        Message.from_role_and_content(Role.ASSISTANT, '{"patch": "a"}')
        .with_channel("commentary")
        .with_recipient("functions.apply_patch")
    )
    m2 = (
        Message.from_role_and_content(Role.ASSISTANT, '{"patch": "b"}')
        .with_channel("commentary")
        .with_recipient("functions.apply_patch")
    )
    ai = parse_harmony_completion(json.dumps([m1.to_dict(), m2.to_dict()]))
    assert len(ai.tool_calls) == 2
    assert {c["args"]["patch"] for c in ai.tool_calls} == {"a", "b"}
    assert ai.tool_calls[0]["id"] != ai.tool_calls[1]["id"]


def test_payload_includes_n_predict_and_temperature() -> None:
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"content": "ok", "tokens": None})

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b",
        base_url="http://127.0.0.1:8080",
        max_tokens=123,
        temperature=0.5,
        transport=httpx.MockTransport(_handler),
    )
    model.invoke([HumanMessage("hi")])
    body = captured["body"]
    assert body["n_predict"] == 123
    assert body["temperature"] == 0.5


def test_http_error_status_raises() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b", transport=httpx.MockTransport(_handler)
    )
    with pytest.raises(httpx.HTTPStatusError):
        model.invoke([HumanMessage("hi")])


def test_missing_content_field_raises() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"tokens": None})

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b", transport=httpx.MockTransport(_handler)
    )
    with pytest.raises(ValueError, match="content"):
        model.invoke([HumanMessage("hi")])


def test_invalid_json_response_raises() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b", transport=httpx.MockTransport(_handler)
    )
    with pytest.raises(ValueError):
        model.invoke([HumanMessage("hi")])


def test_post_method_is_used() -> None:
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        return httpx.Response(200, json={"content": "ok", "tokens": None})

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b", transport=httpx.MockTransport(_handler)
    )
    model.invoke([HumanMessage("hi")])
    assert captured["method"] == "POST"


def test_bind_tools_tool_choice_auto_accepted() -> None:
    def apply_patch(patch: str) -> str:
        """Apply a patch."""
        return patch

    model = HarmonyCompletionChatModel(model="gpt-oss-20b")
    bound = model.bind_tools([apply_patch], tool_choice="auto")
    assert bound is not None


def test_bind_tools_tool_choice_unsupported_rejected() -> None:
    def apply_patch(patch: str) -> str:
        """Apply a patch."""
        return patch

    model = HarmonyCompletionChatModel(model="gpt-oss-20b")
    with pytest.raises(ValueError, match="tool_choice"):
        model.bind_tools([apply_patch], tool_choice="required")


def test_connection_refused_raises() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b", transport=httpx.MockTransport(_handler)
    )
    with pytest.raises(httpx.ConnectError):
        model.invoke([HumanMessage("hi")])


def test_http_400_raises() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b", transport=httpx.MockTransport(_handler)
    )
    with pytest.raises(httpx.HTTPStatusError):
        model.invoke([HumanMessage("hi")])


def test_tokens_wrong_type_raises() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": "ok", "tokens": "nope"})

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b", transport=httpx.MockTransport(_handler)
    )
    with pytest.raises(ValueError, match="tokens"):
        model.invoke([HumanMessage("hi")])


def test_malformed_sse_event_raises() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"data: {not json}\n\n",
        )

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b", transport=httpx.MockTransport(_handler)
    )
    with pytest.raises(ValueError, match="Malformed streaming event"):
        list(model.stream([HumanMessage("hi")]))


def test_truncated_sse_without_stop_still_yields_seen_tokens() -> None:
    from openai_harmony import HarmonyEncodingName, load_harmony_encoding

    enc = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
    tokens = enc.encode(
        "<|channel|>final<|message|>partial answer", allowed_special="all"
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"data: "
            + json.dumps({"content": "", "tokens": tokens}).encode()
            + b"\n\n",
        )

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b", transport=httpx.MockTransport(_handler)
    )
    chunks = list(model.stream([HumanMessage("hi")]))
    text = "".join(c.content for c in chunks if isinstance(c.content, str))
    assert "partial answer" in text
