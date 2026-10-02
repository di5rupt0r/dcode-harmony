from __future__ import annotations

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
