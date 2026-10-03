"""Live tests against a real llama-server on 127.0.0.1:8080.

Skipped only when the server is unavailable. When available, these tests are
strict: they fail on wrong shapes, missing fields, raw Harmony leakage, or a
missing real `apply_patch` tool call. Model responses on this CPU-only,
low-RAM host are slow, so generous timeouts are used.
"""

from __future__ import annotations

import json

import httpx
import pytest

BASE = "http://127.0.0.1:8080"
TIMEOUT = 240.0


def _available() -> bool:
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{BASE}/health")
        return r.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


requires_server = pytest.mark.skipif(
    not _available(), reason="llama-server unavailable"
)
pytestmark = pytest.mark.live


@requires_server
def test_live_health() -> None:
    with httpx.Client(timeout=10.0) as client:
        r = client.get(f"{BASE}/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


@requires_server
def test_live_completion_contract_with_token_prompt() -> None:
    from langchain_core.messages import HumanMessage
    from openai_harmony import HarmonyEncodingName, Role, load_harmony_encoding

    from dcode_harmony.providers.harmony import build_harmony_conversation

    enc = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
    prompt = enc.render_conversation_for_completion(
        build_harmony_conversation([HumanMessage("Say hi in one word")]),
        Role.ASSISTANT,
    )
    assert isinstance(prompt, list) and all(isinstance(t, int) for t in prompt)

    r = httpx.post(
        f"{BASE}/completion",
        json={
            "prompt": prompt,
            "n_predict": 16,
            "temperature": 0.0,
            "stop": ["<|return|>", "<|call|>"],
            "return_tokens": True,
        },
        timeout=TIMEOUT,
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("content"), str)
    assert isinstance(body.get("tokens"), list)
    assert body.get("stop") in (True, "<|return|>", "<|call|>", "content")


@requires_server
def test_live_provider_invoke_returns_valid_ai_message(tracing_transport) -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    from dcode_harmony.providers.harmony import HarmonyCompletionChatModel

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b", timeout_s=TIMEOUT, transport=tracing_transport
    )
    result = model.invoke([HumanMessage("Reply with exactly: ok")])
    assert isinstance(result, AIMessage)
    assert isinstance(result.content, str) and result.content.strip()
    assert "<|" not in result.content  # no raw Harmony markup leaks


@requires_server
def test_live_provider_stream_emits_multiple_chunks(tracing_transport) -> None:
    from langchain_core.messages import HumanMessage

    from dcode_harmony.providers.harmony import HarmonyCompletionChatModel

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b", timeout_s=TIMEOUT, transport=tracing_transport
    )
    chunks = list(model.stream([HumanMessage("Count from 1 to 3, comma separated")]))
    contents = [c.content for c in chunks if isinstance(c.content, str) and c.content]
    assert len(contents) >= 2
    text = "".join(contents)
    assert "1" in text and "2" in text
    assert "<|" not in text


@requires_server
def test_live_apply_patch_tool_call_executes(tmp_path, tracing_transport) -> None:
    from langchain_core.messages import HumanMessage

    from dcode_harmony.providers.harmony import HarmonyCompletionChatModel
    from dcode_harmony.tools.apply_patch import apply_patch_text

    def apply_patch(patch: str) -> str:
        """Apply a patch inside the workspace."""
        return patch

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b", timeout_s=TIMEOUT, transport=tracing_transport
    )
    result = model.bind_tools([apply_patch]).invoke(
        [
            HumanMessage(
                "You MUST call apply_patch to create hello.txt containing 'hi'. "
                "Do not respond in plain text."
            )
        ]
    )
    assert result.tool_calls, f"expected apply_patch tool call, got: {result.content!r}"
    tool_call = result.tool_calls[0]
    assert tool_call["name"] == "apply_patch"
    assert isinstance(tool_call["args"], dict)
    assert isinstance(tool_call["args"].get("patch"), str)

    outcome = apply_patch_text(tool_call["args"]["patch"], workspace=tmp_path)
    assert "hello.txt" in outcome
    target = tmp_path / "hello.txt"
    assert target.exists()
    assert "hi" in target.read_text(encoding="utf-8")


@requires_server
def test_live_sse_fields_and_stop_tokens() -> None:
    from langchain_core.messages import HumanMessage
    from openai_harmony import HarmonyEncodingName, Role, load_harmony_encoding

    from dcode_harmony.providers.harmony import build_harmony_conversation

    enc = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
    prompt = enc.render_conversation_for_completion(
        build_harmony_conversation([HumanMessage("Say one word")]), Role.ASSISTANT
    )
    seen_fields: set[str] = set()
    saw_done = False
    saw_stop = False
    with (
        httpx.Client(timeout=TIMEOUT) as client,
        client.stream(
            "POST",
            f"{BASE}/completion",
            json={
                "prompt": prompt,
                "n_predict": 16,
                "temperature": 0.0,
                "stop": ["<|return|>", "<|call|>"],
                "return_tokens": True,
                "stream": True,
            },
        ) as r,
    ):
        assert r.status_code == 200
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                saw_done = True
                break
            event = json.loads(data)
            seen_fields.update(event.keys())
            if event.get("stop") is True:
                saw_stop = True
    assert "content" in seen_fields
    assert "tokens" in seen_fields
    # llama-server /completion streams end with a stop:true event and close;
    # it does not send a "[DONE]" sentinel.
    assert saw_stop or saw_done
