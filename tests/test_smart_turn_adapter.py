from __future__ import annotations

import numpy as np

from eot_harness.smart_turn_adapter import HaanAudioAdapter, SmartTurnAudioAdapter


class _FakeFeatureExtractor:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, audio_slice, **kwargs):
        self.calls.append((np.asarray(audio_slice), kwargs))
        arr = np.asarray(audio_slice, dtype=np.float32)
        return type("Features", (), {"input_features": np.asarray([[arr[:4]]], dtype=np.float32)})()


class _FakeSession:
    def __init__(self) -> None:
        self.last_inputs = None

    def run(self, _, inputs):
        self.last_inputs = inputs
        values = inputs["input_features"][:, 0, 0]
        return [values.reshape(-1, 1)]


def test_smart_turn_adapter_left_pads_short_audio_and_ignores_messages(monkeypatch) -> None:
    fake_session = _FakeSession()
    fake_extractor = _FakeFeatureExtractor()

    monkeypatch.setattr(
        "eot_harness.smart_turn_adapter._load_smart_turn_session",
        lambda **_: fake_session,
    )
    monkeypatch.setattr(
        "eot_harness.smart_turn_adapter._load_smart_turn_feature_extractor",
        lambda **_: fake_extractor,
    )

    adapter = SmartTurnAudioAdapter(chunk_length_sec=1.0)
    assert adapter.score_point == 0.2
    assert adapter.display_name == "SmartTurn v3.2"
    scores = adapter.predict_batch(
        [
            {
                "audio": {"array": np.array([1.0, 2.0, 3.0], dtype=np.float32), "sampling_rate": 16000},
                "messages": [{"role": "assistant", "content": "ignored"}],
            },
        ],
    )

    assert len(scores) == 1
    padded_audio, kwargs = fake_extractor.calls[0]
    assert padded_audio.shape[0] == adapter.max_samples
    assert np.allclose(padded_audio[-3:], np.array([1.0, 2.0, 3.0], dtype=np.float32))
    assert np.allclose(padded_audio[:-3], 0.0)
    assert kwargs["sampling_rate"] == 16000
    assert kwargs["do_normalize"] is True
    assert fake_session.last_inputs["input_features"].shape == (1, 1, 4)


def test_haan_adapter_loads_haan_weights_with_smart_turn_preprocessing(monkeypatch) -> None:
    loaded = {}

    def fake_load_session(**kwargs):
        loaded.update(kwargs)
        return _FakeSession()

    monkeypatch.setattr("eot_harness.smart_turn_adapter._load_smart_turn_session", fake_load_session)
    monkeypatch.setattr(
        "eot_harness.smart_turn_adapter._load_smart_turn_feature_extractor",
        lambda **_: _FakeFeatureExtractor(),
    )

    adapter = HaanAudioAdapter(chunk_length_sec=1.0)
    assert loaded["model_id"] == "CharanSripadi/haan"
    assert loaded["audio_model_filename"] == "haan-telephony.onnx"
    assert adapter.adapter_id == "CharanSripadi/haan-haan-telephony"
    assert adapter.display_name == "haan (SmartTurn v3.2 phone-audio fine-tune)"
    assert adapter.score_point == SmartTurnAudioAdapter.score_point
    scores = adapter.predict_batch(
        [{"audio": {"array": np.array([1.0, 2.0], dtype=np.float32), "sampling_rate": 16000}}],
    )
    assert len(scores) == 1
