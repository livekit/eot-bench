from __future__ import annotations

import pytest

from eot_harness.livekit_inference import inference_headers, inference_ws_url


def test_inference_ws_url_uses_the_configured_gateway(monkeypatch):
    monkeypatch.setenv("LIVEKIT_INFERENCE_URL", "https://gateway.example.com/v1/")

    assert inference_ws_url("live/sessions", model="openai/gpt-live-1") == (
        "wss://gateway.example.com/v1/live/sessions?model=openai%2Fgpt-live-1"
    )


def test_inference_headers_require_livekit_credentials(monkeypatch):
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="LIVEKIT_API_KEY"):
        inference_headers()


def test_inference_headers_sign_a_bearer_token(monkeypatch):
    monkeypatch.setenv("LIVEKIT_API_KEY", "key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret-that-is-long-enough-for-hmac-signing")

    assert inference_headers()["Authorization"].startswith("Bearer ")
