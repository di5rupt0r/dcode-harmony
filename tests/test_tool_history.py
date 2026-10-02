"""Failing-first tests for tool-call history round-tripping (PR review §2, §3)."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from dcode_harmony.providers.harmony import build_harmony_conversation
from openai_harmony import HarmonyEncodingName, load_harmony_encoding

_ENCODING = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)


def _render(messages) -> str:
    conv = build_harmony_conversation(messages)
    return _ENCODING.decode(_ENCODING.render_conversation(conv))


def test_assistant_tool_calls_render_as_functions_recipient() -> None:
    rendered = _render(
        [
            SystemMessage("rules"),
            HumanMessage("apply it"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "apply_patch",
                        "args": {"patch": "*** Begin Patch\n*** End Patch\n"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
        ]
    )
    assert "to=functions.apply_patch" in rendered
    assert '"patch"' in rendered
    assert "<|call|>" in rendered


def test_tool_message_renders_as_tool_author() -> None:
    rendered = _render(
        [
            HumanMessage("do it"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "apply_patch",
                        "args": {"patch": "x"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(content="Updated a.txt", tool_call_id="call_1", name="apply_patch"),
        ]
    )
    # Tool response rendered with the tool author, not as a user message.
    assert "<|start|>apply_patch<|message|>Updated a.txt<|end|>" in rendered
    assert "user<|message|>Updated a.txt" not in rendered


def test_ai_message_content_preserved_alongside_tool_call() -> None:
    rendered = _render(
        [
            AIMessage(
                content="Let me patch that.",
                tool_calls=[
                    {
                        "name": "apply_patch",
                        "args": {"patch": "x"},
                        "id": "call_9",
                        "type": "tool_call",
                    }
                ],
            ),
        ]
    )
    assert "Let me patch that." in rendered
    assert "to=functions.apply_patch" in rendered
