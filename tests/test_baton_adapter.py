from __future__ import annotations

import asyncio
import base64
import json

import numpy as np
import pytest

from eot_harness import baton_adapter as mod
from eot_harness.baton_adapter import BatonAdapter, _is_transient_error, _prepare_pcm16_audio


class FakeHTTP:
    """Minimal aiohttp double: records the request, replays a scripted response."""

    def __init__(self, body=None, *, status=200, text=""):
        self._body = body if body is not None else {"events": [{"timestamp": 0.1, "p_eot": 0.1}]}
        self._status = status
        self._text = text
        self.url = None
        self.payload = None
        self.headers = None

    # -- aiohttp module surface --
    def ClientTimeout(self, **kw):
        return kw

    def ClientSession(self, **kw):
        return self

    # -- session --
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, *, json=None, headers=None):
        self.url = url
        self.payload = json
        self.headers = headers
        return self

    # -- response --
    @property
    def status(self):
        return self._status

    async def json(self):
        return self._body

    async def text(self):
        return self._text


def _install(monkeypatch, http):
    monkeypatch.setattr(mod, "_import_aiohttp", lambda: http)
    return http


def _row(**over):
    row = {
        "id": "turn-1",
        "audio": {"array": np.zeros(16000, dtype=np.float32), "sampling_rate": 16000},
        "silence_spans": [{"start": 0.5, "end": 0.9}],
        "messages": [{"role": "assistant", "content": "how can I help?"}],
        "words": [{"word": "leaked", "end": 0.4}],
    }
    row.update(over)
    return row


def _run(adapter, row, **kw):
    return asyncio.run(adapter.predict_turn(row, **kw))


# ---- identity -------------------------------------------------------------

def test_adapter_id_is_namespaced():
    assert BatonAdapter().adapter_id == "joinin/baton-v1"


def test_adapter_id_tracks_model_override():
    assert BatonAdapter(model="baton-v2").adapter_id == "joinin/baton-v2"


def test_score_point_matches_published_basis():
    assert BatonAdapter.score_point == 0.2
    assert BatonAdapter.display_name == "Baton"


def test_supports_every_benchmark_language():
    adapter = BatonAdapter()
    assert adapter.supports_language("en")
    assert adapter.supports_language("de")


# ---- PCM16 encoding -------------------------------------------------------

def test_pcm16_uses_32768_scale_not_32767():
    row = _row(audio={"array": np.array([0.5], dtype=np.float32), "sampling_rate": 16000})
    pcm, _ = _prepare_pcm16_audio(row)
    assert np.frombuffer(pcm, dtype=np.int16)[0] == 16384  # 0.5 * 32768


def test_pcm16_clips_to_int16_range():
    row = _row(audio={"array": np.array([1.0, -1.0, 2.0], dtype=np.float32), "sampling_rate": 16000})
    pcm, _ = _prepare_pcm16_audio(row)
    assert np.frombuffer(pcm, dtype=np.int16).tolist() == [32767, -32768, 32767]


def test_pcm16_reports_duration_in_seconds():
    row = _row(audio={"array": np.zeros(8000, dtype=np.float32), "sampling_rate": 16000})
    _, audio_sec = _prepare_pcm16_audio(row)
    assert audio_sec == pytest.approx(0.5)


# ---- event mapping --------------------------------------------------------

def test_events_are_mapped_from_response(monkeypatch):
    http = _install(monkeypatch, FakeHTTP({"events": [
        {"timestamp": 0.1, "p_eot": 0.01},
        {"timestamp": 0.2, "p_eot": 0.87},
    ]}))
    out = _run(BatonAdapter(api_key="k"), _row())
    assert out["events"] == [
        {"timestamp": 0.1, "p_eot": 0.01},
        {"timestamp": 0.2, "p_eot": 0.87},
    ]
    assert out["id"] == "turn-1"
    assert http.url.endswith("/v1/turn")
    assert http.headers == {"X-API-Key": "k"}


def test_incomplete_events_are_skipped(monkeypatch):
    _install(monkeypatch, FakeHTTP({"events": [
        {"words": ["partial"]},
        {"timestamp": 0.3},
        {"p_eot": 0.5},
        {"timestamp": 0.4, "p_eot": 0.9},
    ]}))
    out = _run(BatonAdapter(api_key="k"), _row())
    assert out["events"] == [{"timestamp": 0.4, "p_eot": 0.9}]


def test_non_200_raises_with_detail(monkeypatch):
    _install(monkeypatch, FakeHTTP(status=401, text="invalid or missing X-API-Key"))
    with pytest.raises(RuntimeError, match="401"):
        _run(BatonAdapter(api_key="k", max_retries=0), _row())


def test_prediction_rows_are_built(monkeypatch):
    _install(monkeypatch, FakeHTTP({"events": [{"timestamp": 0.5, "p_eot": 0.4}]}))
    out = _run(BatonAdapter(api_key="k"), _row())
    assert out["prediction_rows"], "one row per silence-span grid point expected"
    assert all(r["p_eot"] == pytest.approx(0.4) for r in out["prediction_rows"])


# ---- the contract that matters -------------------------------------------

def test_only_prior_messages_are_sent_never_the_in_progress_words(monkeypatch):
    """Baton must not see the turn it is being asked to judge."""
    http = _install(monkeypatch, FakeHTTP({"events": [{"timestamp": 0.1, "p_eot": 0.1}]}))
    _run(BatonAdapter(api_key="k"), _row())
    assert http.payload["messages"] == [{"role": "assistant", "content": "how can I help?"}]
    assert "leaked" not in json.dumps(http.payload["messages"])


def test_audio_is_sent_base64_in_one_request(monkeypatch):
    http = _install(monkeypatch, FakeHTTP({"events": [{"timestamp": 0.1, "p_eot": 0.1}]}))
    _run(BatonAdapter(api_key="k"), _row())
    # 1 s of 16 kHz mono PCM16 = 32000 bytes, in a single call.
    assert len(base64.b64decode(http.payload["audio_pcm16_b64"])) == 32000
    assert http.payload["sample_rate"] == 16000


def test_inference_interval_is_forwarded(monkeypatch):
    http = _install(monkeypatch, FakeHTTP({"events": [{"timestamp": 0.1, "p_eot": 0.1}]}))
    _run(BatonAdapter(api_key="k"), _row(), inference_interval=0.25)
    assert http.payload["inference_interval"] == 0.25


# ---- auth and retries -----------------------------------------------------

def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("BATON_API_KEY", raising=False)
    _install(monkeypatch, FakeHTTP())
    with pytest.raises(RuntimeError, match="BATON_API_KEY"):
        _run(BatonAdapter(), _row())


def test_transient_errors_are_classified():
    assert _is_transient_error(asyncio.TimeoutError())
    assert _is_transient_error(ConnectionError("reset by peer"))
    assert _is_transient_error(mod.BatonHTTPError(502, "bad gateway"))
    assert not _is_transient_error(mod.BatonHTTPError(503, "busy"))  # capacity, not transient
    assert not _is_transient_error(mod.BatonHTTPError(401, "invalid key"))
    assert not _is_transient_error(RuntimeError("HTTP 503 mentioned in a message"))
    assert not _is_transient_error(ValueError("bad audio"))


def test_capacity_errors_are_retried_until_they_succeed(monkeypatch):
    """A 429 must never cost a turn: it is the server being busy, not broken.

    A dropped turn vanishes from the metrics with nothing in the output saying so,
    and would read as the model failing rather than the service being loaded.
    """
    calls = {"n": 0}

    class Flaky(FakeHTTP):
        def post(self, url, *, json=None, headers=None):
            # count per REQUEST, not per status read -- the error message reads
            # .status too, which would double-count
            calls["n"] += 1
            self._status = 429 if calls["n"] <= 3 else 200
            return super().post(url, json=json, headers=headers)

    http = _install(monkeypatch, Flaky({"events": [{"timestamp": 0.1, "p_eot": 0.7}]}))
    real_sleep = asyncio.sleep          # capture before patching, or it recurses
    monkeypatch.setattr(mod.asyncio, "sleep", lambda *_a, **_k: real_sleep(0))
    out = _run(BatonAdapter(api_key="k", retry_backoff=0.0), _row())
    assert out["events"] == [{"timestamp": 0.1, "p_eot": 0.7}]
    assert calls["n"] == 4, f"expected 3 rejections then success, got {calls['n']} requests"


def test_capacity_retries_are_separate_from_transient_retries():
    a = BatonAdapter()
    assert a.capacity_retries > a.max_retries, "429 needs a more patient budget"
    assert mod._is_capacity_error(mod.BatonHTTPError(429, "busy"))
    assert mod._is_capacity_error(mod.BatonHTTPError(503, "scaling"))
    assert not mod._is_capacity_error(mod.BatonHTTPError(401, "invalid key"))
    # Classification is by status code, never by digits in the response body.
    assert not mod._is_capacity_error(mod.BatonHTTPError(422, "expected 16000 samples, got 4290"))
    assert not mod._is_capacity_error(RuntimeError("HTTP 429"))


def test_accepts_the_raw_undecoded_audio_shape(monkeypatch):
    """Streaming adapters get Audio(decode=False): {bytes, path}, not {array, ...}.

    Assuming the decoded shape passes every synthetic-row test and then KeyErrors on
    the first real dataset turn.
    """
    import io as _io, wave as _wave
    buf = _io.BytesIO()
    with _wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(np.zeros(1600, dtype="<i2").tobytes())
    raw = {"bytes": buf.getvalue(), "path": "x.wav"}
    pcm, secs = mod._prepare_pcm16_audio({"audio": raw})
    assert len(pcm) == 3200
    assert secs == pytest.approx(0.1, abs=0.01)


def test_empty_events_raise_instead_of_scoring_zero(monkeypatch):
    """An empty grid must fail loudly, not score every span as p_eot=0."""
    _install(monkeypatch, FakeHTTP({"events": []}))
    with pytest.raises(RuntimeError, match="No Baton events"):
        _run(BatonAdapter(api_key="k"), _row())


def test_malformed_body_raises_clearly(monkeypatch):
    _install(monkeypatch, FakeHTTP({"events": None}))
    with pytest.raises(RuntimeError, match="no 'events' list"):
        _run(BatonAdapter(api_key="k"), _row())


def test_permanent_errors_are_not_retried(monkeypatch):
    calls = {"n": 0}

    class Bad(FakeHTTP):
        def post(self, url, *, json=None, headers=None):
            calls["n"] += 1
            return super().post(url, json=json, headers=headers)

    _install(monkeypatch, Bad(status=422, text="expected 16000 samples, got 4290 (see 503 docs)"))
    with pytest.raises(mod.BatonHTTPError, match="422"):
        _run(BatonAdapter(api_key="k", retry_backoff=0.0), _row())
    assert calls["n"] == 1


def test_capacity_budget_is_exhausted_without_falling_into_transient_budget(monkeypatch):
    calls = {"n": 0}

    class Busy(FakeHTTP):
        def post(self, url, *, json=None, headers=None):
            calls["n"] += 1
            return super().post(url, json=json, headers=headers)

    _install(monkeypatch, Busy(status=503, text="scaling"))
    with pytest.raises(mod.BatonHTTPError, match="503"):
        _run(BatonAdapter(api_key="k", retry_backoff=0.0, capacity_retries=2, max_retries=4), _row())
    assert calls["n"] == 3  # 1 + capacity_retries, transient budget untouched


def test_stereo_audio_is_downmixed_at_native_rate():
    stereo = np.stack([np.full(1600, 0.5, dtype=np.float32), np.full(1600, -0.5, dtype=np.float32)], axis=1)
    pcm, secs = _prepare_pcm16_audio({"audio": {"array": stereo, "sampling_rate": 16000}})
    assert len(pcm) == 3200  # mono frames, not interleaved stereo
    assert secs == pytest.approx(0.1)
    assert np.frombuffer(pcm, dtype=np.int16).max() == 0


def test_concurrency_is_exposed_to_the_harness():
    assert BatonAdapter().concurrency == mod.DEFAULT_CONCURRENCY
    assert BatonAdapter(concurrency=2).concurrency == 2
    with pytest.raises(ValueError):
        BatonAdapter(concurrency=0)
    with pytest.raises(ValueError):
        BatonAdapter(timeout=0)
