"""Connection helpers for provider models served through LiveKit Inference."""

from __future__ import annotations

import os
from urllib.parse import urlencode


def inference_ws_url(path: str, *, model: str) -> str:
    """Websocket URL for `path` on the LiveKit Inference gateway, with the model as a query parameter."""
    base_url = _auth().get_default_inference_url().rstrip("/")
    if base_url.startswith(("http://", "https://")):
        base_url = base_url.replace("http", "ws", 1)
    return f"{base_url}/{path.strip('/')}?{urlencode({'model': model})}"


def inference_headers() -> dict[str, str]:
    """Gateway headers with a fresh access token signed from LIVEKIT_API_KEY and LIVEKIT_API_SECRET."""
    api_key = os.environ.get("LIVEKIT_API_KEY")
    api_secret = os.environ.get("LIVEKIT_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError("LiveKit Inference adapters require LIVEKIT_API_KEY and LIVEKIT_API_SECRET.")
    auth = _auth()
    return {
        **auth.get_inference_headers(),
        "Authorization": f"Bearer {auth.create_access_token(api_key, api_secret)}",
    }


def _auth():
    try:
        from livekit.agents.inference import _utils
    except ImportError as exc:
        raise RuntimeError("LiveKit Inference adapters require `livekit-agents` for gateway auth.") from exc
    return _utils
