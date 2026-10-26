from __future__ import annotations

import base64
import io
import wave

import numpy as np
import pytest

from eot_harness import duplexjev_adapter as mod
from eot_harness.duplexjev_adapter import DuplexJevContextAdapter, _assistant_said


class FakeResponse:
    def __init__(self, probs, status=200):
        self._probs = probs
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"answers": {"turn": {"probs": self._probs}}}


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, *, json=None, timeout=None):
        self.calls.append((url, json))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _item(**kw):
    item = {"audio": {"array": np.zeros(16000, dtype=np.float32), "sampling_rate": 16000}, "language": "en"}
    item.update(kw)
    return item


def _adapter(monkeypatch, responses):
    monkeypatch.setenv("DUPLEXJEV_GATEWAY", "http://gw.test/")
    a = DuplexJevContextAdapter()
    a._session = FakeSession(responses)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    return a


def test_score_is_finished_plus_backchannel(monkeypatch):
    q = mod.TURN_QUESTION["en"]["options"]
    a = _adapter(monkeypatch, [FakeResponse({q[0]: 0.5, q[1]: 0.2, q[2]: 0.25, q[3]: 0.05})])
    assert a.predict_batch([_item()]) == [pytest.approx(0.75)]
    url, payload = a._session.calls[0]
    assert url == "http://gw.test/v1/decide"
    assert payload["questions"][0]["text"] == "Has the user finished speaking?"


def test_never_reads_user_words(monkeypatch):
    class Boom(dict):
        def __getitem__(self, k):
            if k == "words":
                raise AssertionError("adapter must not read row['words']")
            return super().__getitem__(k)

        def get(self, k, default=None):
            if k == "words":
                raise AssertionError("adapter must not read row['words']")
            return super().get(k, default)

    a = _adapter(monkeypatch, [FakeResponse({mod.TURN_QUESTION["en"]["options"][0]: 1.0})])
    a.predict_batch([Boom(_item(words=["secret"]))])
    assert "secret" not in str(a._session.calls[0][1])


def test_sends_only_last_assistant_message(monkeypatch):
    msgs = [
        {"role": "assistant", "content": "first"},
        {"role": "user", "content": "user text must not be sent"},
        {"role": "assistant", "content": "x" * 400},
    ]
    a = _adapter(monkeypatch, [FakeResponse({})])
    a.predict_batch([_item(messages=msgs)])
    payload = a._session.calls[0][1]
    assert payload["assistant_said"] == "x" * 300
    assert "user text" not in str(payload)


def test_no_context_when_disabled_or_absent(monkeypatch):
    monkeypatch.setenv("DUPLEXJEV_CONTEXT", "0")
    a = _adapter(monkeypatch, [FakeResponse({})])
    a.predict_batch([_item(messages=[{"role": "assistant", "content": "hi"}])])
    assert "assistant_said" not in a._session.calls[0][1]
    assert _assistant_said(None) == ""


def test_chinese_question_and_english_fallback(monkeypatch):
    a = _adapter(monkeypatch, [FakeResponse({}), FakeResponse({})])
    a.predict_batch([_item(language="zh"), _item(language="ja")])
    assert a._session.calls[0][1]["lang"] == "zh"
    assert a._session.calls[1][1]["lang"] == "en"
    assert all(a.supports_language(l) for l in ["en", "zh", "ja", "ar"])


def test_audio_resampled_to_16k_pcm16_and_padded(monkeypatch):
    a = _adapter(monkeypatch, [FakeResponse({}), FakeResponse({})])
    a.predict_batch([_item(audio={"array": np.zeros(48000, dtype=np.float32), "sampling_rate": 48000})])
    a.predict_batch([_item(audio={"array": np.zeros(100, dtype=np.float32), "sampling_rate": 16000})])
    for _, payload, n in [(*a._session.calls[0], 16000), (*a._session.calls[1], 1600)]:
        with wave.open(io.BytesIO(base64.b64decode(payload["audio_b64"]))) as w:
            assert (w.getframerate(), w.getsampwidth(), w.getnchannels(), w.getnframes()) == (16000, 2, 1, n)


def test_retries_then_raises(monkeypatch):
    q0 = mod.TURN_QUESTION["en"]["options"][0]
    a = _adapter(monkeypatch, [RuntimeError("x"), FakeResponse({}, status=503), FakeResponse({q0: 0.9})])
    assert a.predict_batch([_item()]) == [pytest.approx(0.9)]
    b = _adapter(monkeypatch, [RuntimeError("x")] * 4)
    with pytest.raises(RuntimeError):
        b.predict_batch([_item()])
