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
