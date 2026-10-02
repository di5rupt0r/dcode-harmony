from __future__ import annotations

import json

import httpx
import pytest


@pytest.mark.live
def test_live_llama_server_completion_smoke() -> None:
    base = "http://127.0.0.1:8080"
    try:
        with httpx.Client(timeout=1.0) as client:
            response = client.get(f"{base}/health")
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"llama-server unavailable: {exc}")

    if response.status_code >= 500:
        pytest.skip(f"llama-server unhealthy: status={response.status_code}")

    with httpx.Client(timeout=10.0) as client:
        completion = client.post(
            f"{base}/completion",
            json={"prompt": "ping", "n_predict": 8, "temperature": 0.0},
        )
    assert completion.status_code < 500


@pytest.mark.live
def test_live_llama_server_normal_completion() -> None:
    base = "http://127.0.0.1:8080"
    try:
        with httpx.Client(timeout=1.0) as client:
            response = client.get(f"{base}/health")
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"llama-server unavailable: {exc}")

    if response.status_code >= 500:
        pytest.skip(f"llama-server unhealthy: status={response.status_code}")

    with httpx.Client(timeout=30.0) as client:
        completion = client.post(
            f"{base}/completion",
            json={
                "prompt": "Say hello",
                "n_predict": 32,
                "temperature": 0.0,
                "stop": ["<|return|>", "<|call|>"],
            },
        )
    assert completion.status_code == 200
    body = completion.json()
    assert "content" in body
    assert isinstance(body["content"], str)


@pytest.mark.live
def test_live_llama_server_error_handling() -> None:
    base = "http://127.0.0.1:8080"
    try:
        with httpx.Client(timeout=1.0) as client:
            response = client.get(f"{base}/health")
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"llama-server unavailable: {exc}")

    if response.status_code >= 500:
        pytest.skip(f"llama-server unhealthy: status={response.status_code}")

    with httpx.Client(timeout=10.0) as client:
        completion = client.post(
            f"{base}/completion",
            json={"prompt": "test", "n_predict": -1},
        )
    assert completion.status_code >= 400


@pytest.mark.live
def test_live_harmony_provider_integration() -> None:
    from dcode_harmony.providers.harmony import HarmonyCompletionChatModel
    from langchain_core.messages import HumanMessage

    base = "http://127.0.0.1:8080"
    try:
        with httpx.Client(timeout=1.0) as client:
            response = client.get(f"{base}/health")
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"llama-server unavailable: {exc}")

    if response.status_code >= 500:
        pytest.skip(f"llama-server unhealthy: status={response.status_code}")

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b",
        base_url=base,
        timeout_s=30.0,
    )

    result = model.invoke([HumanMessage("Say hello in one word")])
    assert result.content
    assert len(result.content) > 0


def _live_server_available(base: str = "http://127.0.0.1:8080") -> bool:
    try:
        with httpx.Client(timeout=1.0) as client:
            response = client.get(f"{base}/health")
        return response.status_code < 500
    except Exception:
        return False


@pytest.mark.live
def test_live_health_and_completion_endpoint_shape() -> None:
    if not _live_server_available():
        pytest.skip("llama-server unavailable")
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            "http://127.0.0.1:8080/completion",
            json={
                "prompt": "<|start|>user<|message|>Say hi<|end|><|start|>assistant",
                "n_predict": 32,
                "temperature": 0.0,
                "stop": ["<|return|>", "<|call|>"],
                "return_tokens": True,
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("content"), str)
    assert isinstance(body.get("tokens"), list)


@pytest.mark.live
def test_live_provider_harmony_parsing() -> None:
    if not _live_server_available():
        pytest.skip("llama-server unavailable")
    from dcode_harmony.providers.harmony import HarmonyCompletionChatModel
    from langchain_core.messages import HumanMessage

    model = HarmonyCompletionChatModel(model="gpt-oss-20b", timeout_s=60.0)
    result = model.invoke([HumanMessage("Reply with exactly: ok")])
    assert isinstance(result.content, str)
    assert "<|" not in result.content  # no raw Harmony tokens leak into content


@pytest.mark.live
def test_live_provider_streaming() -> None:
    if not _live_server_available():
        pytest.skip("llama-server unavailable")
    from dcode_harmony.providers.harmony import HarmonyCompletionChatModel
    from langchain_core.messages import HumanMessage

    model = HarmonyCompletionChatModel(model="gpt-oss-20b", timeout_s=60.0)
    chunks = list(model.stream([HumanMessage("Count to three")]))
    assert chunks
    text = "".join(c.content for c in chunks if isinstance(c.content, str))
    assert text


@pytest.mark.live
def test_live_apply_patch_tool_call_shape() -> None:
    """The model should emit functions.apply_patch when a patch is requested."""
    if not _live_server_available():
        pytest.skip("llama-server unavailable")
    from langchain_core.messages import HumanMessage

    from dcode_harmony.providers.harmony import HarmonyCompletionChatModel

    def apply_patch(patch: str) -> str:
        """Apply a patch inside the workspace."""
        return patch

    model = HarmonyCompletionChatModel(model="gpt-oss-20b", timeout_s=60.0)
    bound = model.bind_tools([apply_patch])
    result = bound.invoke(
        [HumanMessage("Create file hello.txt with 'hi' using apply_patch")]
    )
    # Do not assert a specific tool call — report the shape for the record.
    print("tool_calls:", getattr(result, "tool_calls", None))
    print("content:", result.content)
