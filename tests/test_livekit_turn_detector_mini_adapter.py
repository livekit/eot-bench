from __future__ import annotations

import sys
import time
import types

import numpy as np
import pytest

from eot_harness import livekit_turn_detector_mini_adapter as module
from eot_harness.livekit_turn_detector_mini_adapter import LiveKitTurnDetectorMiniAdapter


class FakeEOT:
    def __init__(self) -> None:
        self.calls: list[np.ndarray] = []
        self.turn_samples: list[int | None] = []
        self.closed = False

    def predict(self, pcm: np.ndarray, turn_samples: int | None = None) -> float:
        self.calls.append(pcm.copy())
        self.turn_samples.append(turn_samples)
        return float(len(pcm)) / 10.0

    def close(self) -> None:
        self.closed = True


def test_livekit_turn_detector_mini_adapter_defaults(monkeypatch) -> None:
    fake_model = FakeEOT()
    monkeypatch.setattr(module, "_load_local_eot_model", lambda: fake_model)

    adapter = LiveKitTurnDetectorMiniAdapter()

    assert adapter.score_point == 0.2
    assert adapter.display_name == "LiveKit Turn Detector v1.1-mini"
    assert adapter.model_id == "turn-detector-v1.1-mini"
    assert adapter.revision == "livekit-local-inference"
    assert adapter.sample_rate == 16000
    assert adapter.audio_sec == 2.0
    assert adapter.max_audio_sec is None
    assert adapter.max_samples == 32000
    assert adapter.num_workers >= 1
    assert adapter.adapter_id == "livekit/turn-detector-v1.1-mini-livekit-local-inference"
    adapter.close()


def test_livekit_turn_detector_mini_adapter_predicts_pcm16_tail(monkeypatch) -> None:
    monkeypatch.setenv(module.LIVEKIT_TURN_DETECTOR_MINI_WORKERS_ENV, "1")
    fake_model = FakeEOT()
    monkeypatch.setattr(module, "_load_local_eot_model", lambda: fake_model)

    adapter = LiveKitTurnDetectorMiniAdapter(sample_rate=10, audio_sec=0.3)
    scores = adapter.predict_batch(
        [
            {
                "audio": {
                    "array": np.asarray([-1.5, -0.5, 0.0, 0.5, 1.5], dtype=np.float32),
                    "sampling_rate": 10,
                },
                "messages": [{"role": "user", "content": "ignored"}],
            }
        ]
    )

    assert scores == [0.3]
    assert len(fake_model.calls) == 1
    assert fake_model.calls[0].dtype == np.int16
    assert fake_model.calls[0].flags.c_contiguous
    np.testing.assert_array_equal(fake_model.calls[0], np.asarray([0, 16383, 32767], dtype=np.int16))
    assert fake_model.turn_samples == [5]
    adapter.close()
    assert fake_model.closed is True


def test_livekit_turn_detector_mini_adapter_can_predict_in_parallel(monkeypatch) -> None:
    monkeypatch.setenv(module.LIVEKIT_TURN_DETECTOR_MINI_WORKERS_ENV, "2")
    fake_models: list[FakeEOT] = []

    class SlowFakeEOT(FakeEOT):
        def predict(self, pcm: np.ndarray, turn_samples: int | None = None) -> float:
            time.sleep(0.02)
            return super().predict(pcm, turn_samples)

    def fake_load_model():
        model = SlowFakeEOT()
        fake_models.append(model)
        return model

    monkeypatch.setattr(module, "_load_local_eot_model", fake_load_model)

    adapter = LiveKitTurnDetectorMiniAdapter(sample_rate=10, audio_sec=0.3)
    batch = [
        {
            "audio": {
                "array": np.asarray([0.0, 0.25, 0.5, 0.75], dtype=np.float32),
                "sampling_rate": 10,
            },
            "messages": [],
        }
        for _ in range(4)
    ]

    scores = adapter.predict_batch(batch)

    assert scores == [0.3, 0.3, 0.3, 0.3]
    assert adapter.num_workers == 2
    assert len(fake_models) == 2
    assert sum(len(model.calls) for model in fake_models) == 4
    adapter.close()
    assert all(model.closed for model in fake_models)


def test_prepare_pcm16_tail_resamples_and_mixes_channels(monkeypatch) -> None:
    captured = {}

    def fake_resample_audio(array, orig_sr, new_sr):
        captured["array"] = array.copy()
        captured["orig_sr"] = orig_sr
        captured["new_sr"] = new_sr
        return np.asarray([0.25, -0.25], dtype=np.float32)

    monkeypatch.setattr(module, "resample_audio", fake_resample_audio)

    pcm, total_samples = module._prepare_pcm16_tail(
        {
            "audio": {
                "array": np.asarray([[1.0, -1.0], [0.5, 0.0]], dtype=np.float32),
                "sampling_rate": 20,
            }
        },
        sample_rate=10,
        max_samples=10,
    )

    np.testing.assert_array_equal(captured["array"], np.asarray([0.0, 0.25], dtype=np.float32))
    assert captured["orig_sr"] == 20
    assert captured["new_sr"] == 10
    np.testing.assert_array_equal(pcm, np.asarray([8191, -8191], dtype=np.int16))
    assert total_samples == 2


def test_prepare_pcm16_tail_counts_samples_before_cropping() -> None:
    pcm, total_samples = module._prepare_pcm16_tail(
        {"audio": {"array": np.full(7, 0.5, dtype=np.float32), "sampling_rate": 10}},
        sample_rate=10,
        max_samples=3,
    )

    assert total_samples == 7
    np.testing.assert_array_equal(pcm, np.full(3, 16383, dtype=np.int16))


def _install_fake_local_inference(monkeypatch, *, max_samples: int) -> None:
    fake = types.ModuleType("livekit.local_inference")
    fake.EOT = FakeEOT
    fake.EOT_MAX_SAMPLES = max_samples
    monkeypatch.setitem(sys.modules, "livekit.local_inference", fake)


def test_load_local_eot_model_accepts_the_v1_1_mini_window(monkeypatch) -> None:
    _install_fake_local_inference(monkeypatch, max_samples=32000)

    assert isinstance(module._load_local_eot_model(), FakeEOT)


def test_load_local_eot_model_rejects_the_v1_mini_window(monkeypatch) -> None:
    _install_fake_local_inference(monkeypatch, max_samples=19200)

    with pytest.raises(RuntimeError, match="19200-sample EOT window"):
        module._load_local_eot_model()
