from __future__ import annotations

import argparse
import json

import numpy as np
import pytest

from eot_harness import inworld_sava_adapter
from eot_harness.adapters import validate_streaming_adapter
from eot_harness.cli import _streaming_prediction_config
from eot_harness.inworld_sava_adapter import InworldSavaAdapter

FRAME_SAMPLES = 640


@pytest.fixture
def pushed(monkeypatch):
    """Fake the model: frame k (0-based) scores (k + 1) / 100, whole frames only."""
    calls = []

    def frame_scores(model, samples):
        calls.append(samples)
        return np.arange(1, len(samples) // FRAME_SAMPLES + 1, dtype=np.float32) / 100.0

    monkeypatch.setattr(inworld_sava_adapter, "_load_sava", lambda **_: "model")
    monkeypatch.setattr(inworld_sava_adapter, "_frame_scores", frame_scores)
    return calls


def _row(n_samples, spans, sample_rate=16_000, channels=1):
    shape = (n_samples, channels) if channels > 1 else (n_samples,)
    return {
        "id": "turn-1",
        "language": "en",
        "audio": {"array": np.ones(shape, dtype=np.float32), "sampling_rate": sample_rate},
        "silence_spans": [{"start": start, "end": end} for start, end in spans],
    }


def test_score_is_the_last_frame_that_ends_at_or_before_each_timestamp(pushed) -> None:
    adapter = InworldSavaAdapter()
    validate_streaming_adapter(adapter)
    assert adapter.display_name == "Inworld SAVA"
    assert adapter.adapter_id == f"inworld/sava-{inworld_sava_adapter.DEFAULT_REVISION}"
    assert getattr(adapter, "score_point", None) is None
    config = _streaming_prediction_config(adapter, argparse.Namespace(inference_interval=0.1))
    assert json.loads(json.dumps(config))["adapter_id"] == adapter.adapter_id

    # 2.03 s of audio: 50 whole frames and a partial frame that gives no score.
    result = adapter.predict_turn(_row(50 * FRAME_SAMPLES + 480, [(0.5, 0.7), (1.0, 2.03)]), inference_interval=0.1)

    assert result["audio_sec"] == pytest.approx(2.03)
    assert len(result["events"]) == 50
    assert result["events"][0] == {"timestamp": 0.04, "p_eot": pytest.approx(0.01)}
    rows = result["prediction_rows"]
    by_time = {row["timestamp"]: row["p_eot"] for row in rows}
    # 0.5 s is between frame ends 0.48 s and 0.52 s: the span start keeps frame 12.
    assert by_time[0.5] == pytest.approx(0.12)
    assert by_time[0.6] == pytest.approx(0.15)
    assert by_time[0.7] == pytest.approx(0.17)
    assert by_time[1.0] == pytest.approx(0.25)
    assert by_time[2.0] == pytest.approx(0.50)
    assert by_time[2.03] == pytest.approx(0.50)
    assert [row["label"] for row in rows if row["timestamp"] <= 0.7] == ["hold"] * 3
    assert rows[-1]["label"] == "eot"


def test_span_before_the_first_whole_frame_scores_zero(pushed) -> None:
    result = InworldSavaAdapter().predict_turn(_row(FRAME_SAMPLES, [(0.0, 0.1)]), inference_interval=0.1)

    assert [row["p_eot"] for row in result["prediction_rows"]] == [0.0, pytest.approx(0.01)]


def test_audio_is_mono_float32_at_16k(pushed) -> None:
    adapter = InworldSavaAdapter()
    adapter.predict_turn(_row(800, [(0.0, 0.1)], sample_rate=8_000))
    adapter.predict_turn(_row(1600, [(0.0, 0.1)], channels=2))

    assert [samples.shape for samples in pushed] == [(1600,), (1600,)]
    assert all(samples.dtype == np.float32 for samples in pushed)


def test_adapter_supports_all_benchmark_languages(pushed) -> None:
    adapter = InworldSavaAdapter()
    assert adapter.supports_language("en")
    assert adapter.supports_language(" ZH ")
    assert not adapter.supports_language("xx")


def test_loader_gets_the_pinned_model_id_and_revision(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr(inworld_sava_adapter, "_load_sava", lambda **kwargs: seen.append(kwargs))

    InworldSavaAdapter()
    adapter = InworldSavaAdapter(model_id="/weights/sava.safetensors", revision=None, device="cpu")

    assert adapter.adapter_id == "/weights/sava.safetensors"
    assert seen == [
        {"model_id": "inworld/sava", "revision": inworld_sava_adapter.DEFAULT_REVISION, "device": None},
        {"model_id": "/weights/sava.safetensors", "revision": None, "device": "cpu"},
    ]
