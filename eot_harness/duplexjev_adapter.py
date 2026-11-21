"""DuplexJev end-of-turn adapter (Adventists AI, https://github.com/adventists-ai/duplexjev).

DuplexJev is an open-weight speech model that answers multiple-choice questions about raw audio by reading one
token per question. This adapter asks it the same end-of-turn question as ``livekit-plugins-duplexjev``:

- question: "Has the user finished speaking?" with four options (finished / not finished / backchannel / hesitating);
  the end-of-turn score is P(finished) + P(backchannel);
- context: only the last assistant message in ``row["messages"]`` (last 300 characters), which the LiveKit plugin
  also sends (``detector.attach(session)``). The user's transcript (``row["words"]``) is never read: the model only
  hears the user's audio up to the decision point;
- the model was trained on English and Chinese; for the other 12 languages the English question is used.

It calls a ``duplexjev gateway`` (``pip install "duplexjev[server]>=0.6"``) in front of a vLLM server:

    vllm serve adventists-ai/DuplexJev-32B-Para --revision v1.2 --max-model-len 4096 --port 8000
    duplexjev gateway --vllm http://localhost:8000/v1 --port 8420 --rate 1000000
    DUPLEXJEV_GATEWAY=http://localhost:8420 eot-harness predict --path livekit/eot-bench-data --name en \
        --split validation --adapter eot_harness.duplexjev_adapter:DuplexJevContextAdapter --output-dir output

The hosted trial API is rate limited (30 requests/minute), so benchmark runs should use a self-hosted gateway.
"""

from __future__ import annotations

import base64
import io
import os
import time
import wave
from concurrent.futures import ThreadPoolExecutor

import numpy as np

SAMPLE_RATE = 16000

TURN_QUESTION = {
    "en": {
        "id": "turn",
        "text": "Has the user finished speaking?",
        "options": [
            "finished, the assistant can reply",
            "not finished, still talking",
            "just a backchannel, not taking the turn",
            "hesitating or asking to wait",
        ],
        "lang": "en",
    },
    "zh": {
        "id": "turn",
        "text": "用户现在处于什么话轮状态？",
        "options": ["话说完了，可以接话", "句子没说完，还在继续", "简短附和，不是要接话", "还在组织语言，或要求先等一下"],
        "lang": "zh",
    },
}


def _resample(x: np.ndarray, sr: int) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 2:
        x = x.mean(axis=1)
    if sr == SAMPLE_RATE:
        return x
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(int(sr), SAMPLE_RATE)
    return resample_poly(x, SAMPLE_RATE // g, int(sr) // g).astype(np.float32)


def _wav_bytes(x16k: np.ndarray) -> bytes:
    pcm = np.clip(np.asarray(x16k, dtype=np.float32), -1.0, 1.0)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((pcm * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def _assistant_said(messages) -> str:
    prev = [m.get("content") for m in (messages or []) if m.get("role") == "assistant" and m.get("content")]
    return str(prev[-1])[-300:] if prev else ""


class DuplexJevContextAdapter:
    score_point = 0.2
    max_audio_sec = 8.0

    def __init__(self) -> None:
        import requests

        self.gateway = os.environ.get("DUPLEXJEV_GATEWAY", "http://localhost:8420").rstrip("/")
        label = os.environ.get("DUPLEXJEV_MODEL_LABEL", "DuplexJev-32B-Para v1.2")
        self.display_name = label
        self.adapter_id = label.lower().replace(" ", "-")
        self.use_context = os.environ.get("DUPLEXJEV_CONTEXT", "1") != "0"
        self._session = requests.Session()
        self._pool = ThreadPoolExecutor(max_workers=int(os.environ.get("DUPLEXJEV_CONCURRENCY", "32")))

    def supports_language(self, lang_code: str) -> bool:
        return True

    def build_payload(self, item) -> tuple[dict, dict]:
        lang = "zh" if str(item.get("language", "en")).lower() == "zh" else "en"
        q = TURN_QUESTION[lang]
        a = item["audio"]
        x = _resample(np.asarray(a["array"], dtype=np.float32), int(a["sampling_rate"]))
        if len(x) < SAMPLE_RATE // 10:
            x = np.pad(x, (SAMPLE_RATE // 10 - len(x), 0))
        payload = {
            "audio_b64": base64.b64encode(_wav_bytes(x)).decode(),
            "format": "wav",
            "lang": q["lang"],
            "questions": [q],
        }
        said = _assistant_said(item.get("messages")) if self.use_context else ""
        if said:
            payload["assistant_said"] = said
        return payload, q

    def _one(self, item) -> float:
        payload, q = self.build_payload(item)
        for attempt in range(4):
            try:
                r = self._session.post(self.gateway + "/v1/decide", json=payload, timeout=60)
                r.raise_for_status()
                p = r.json()["answers"]["turn"]["probs"]
                return float(p.get(q["options"][0], 0.0)) + float(p.get(q["options"][2], 0.0))
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(1.0 + attempt)
        raise RuntimeError("unreachable")

    def predict_batch(self, batch):
        return list(self._pool.map(self._one, batch))
