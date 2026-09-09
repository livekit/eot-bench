from __future__ import annotations

import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest

from eot_harness import vap_adapter
from eot_harness.vap_adapter import VAPAdapter


@pytest.fixture
def waveforms(monkeypatch):
    calls = []
    monkeypatch.setattr(vap_adapter, "_load_vap_model", lambda **_: object())

    def predict(model, waveform):
        calls.append(waveform)
        return float(waveform[0, 0, -1])

    monkeypatch.setattr(vap_adapter, "_predict_eot", predict)
    return calls


def _item(array, sample_rate=16_000):
    return {
        "audio": {"array": np.asarray(array), "sampling_rate": sample_rate},
        "messages": [{"role": "assistant", "content": "ignored"}],
    }


def test_vap_keeps_user_audio_and_agent_silence_separate(waveforms):
    adapter = VAPAdapter()
    arrays = [np.linspace(0.0, 0.8, 1600), np.linspace(0.0, 0.3, 3200)]

    assert adapter.predict_batch([_item(array) for array in arrays]) == pytest.approx([0.8, 0.3])
    for waveform, array in zip(waveforms, arrays):
        assert waveform.shape == (1, 2, len(array))
        assert waveform.dtype == np.float32
        np.testing.assert_allclose(waveform[0, 0], array)
        assert np.count_nonzero(waveform[0, 1]) == 0
    assert adapter.predict_batch([]) == []


def test_vap_bounds_context_before_resampling(monkeypatch, waveforms):
    adapter = VAPAdapter(max_audio_sec=1.0)
    array = np.arange(24_000, dtype=np.float32)

    def resample(prefix, *, sample_rate):
        assert sample_rate == 8000
        np.testing.assert_array_equal(prefix, array[-8000:])
        return np.repeat(prefix, 2)

    monkeypatch.setattr(vap_adapter, "_resample_audio", resample)
    adapter.predict_batch([_item(array, 8000)])

    assert waveforms[0].shape == (1, 2, 16_000)
    np.testing.assert_array_equal(waveforms[0][0, 0], np.repeat(array[-8000:], 2))


def test_vap_left_pads_only_prefixes_shorter_than_one_frame(waveforms):
    adapter = VAPAdapter()
    adapter.predict_batch([_item([]), _item([0.1, 0.2, 0.3])])

    assert waveforms[0].shape == (1, 2, 320)
    assert np.count_nonzero(waveforms[0]) == 0
    assert waveforms[1].shape == (1, 2, 320)
    np.testing.assert_allclose(waveforms[1][0, 0, -3:], [0.1, 0.2, 0.3])
    assert np.count_nonzero(waveforms[1][0, 0, :-3]) == 0
    assert np.count_nonzero(waveforms[1][0, 1]) == 0


def test_vap_rejects_non_mono_audio_and_invalid_sample_rates(waveforms):
    adapter = VAPAdapter()
    with pytest.raises(ValueError, match="mono audio"):
        adapter.predict_batch([_item(np.zeros((2, 1600)))])
    with pytest.raises(ValueError, match="sampling_rate must be positive"):
        adapter.predict_batch([_item([0.1], 0)])
    assert waveforms == []


@pytest.mark.parametrize("max_audio_sec", [0, -1, 0.01, float("nan"), float("inf")])
def test_vap_rejects_invalid_context_before_loading_model(max_audio_sec):
    with pytest.raises(ValueError, match="max_audio_sec"):
        VAPAdapter(max_audio_sec=max_audio_sec)


def test_vap_uses_last_frame_user_p_now():
    torch = pytest.importorskip("torch")
    logits = torch.tensor([[[9.0, 1.0], [1.0, 2.0]]])

    class Objective:
        def probs_next_speaker_aggregate(self, probs, *, from_bin, to_bin):
            assert (from_bin, to_bin) == (0, 1)
            torch.testing.assert_close(probs, logits[:, -1:, :].softmax(dim=-1))
            return torch.tensor([[[0.8, 0.3]]])

    class Model(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.zeros(1))
            self.objective = Objective()

        def forward(self, waveform):
            assert torch.is_inference_mode_enabled()
            assert waveform.shape == (1, 2, 320)
            return {"logits": logits}

    score = vap_adapter._predict_eot(Model(), np.zeros((1, 2, 320), dtype=np.float32))
    assert score == pytest.approx(0.2)


@pytest.mark.parametrize("wrapped", [False, True])
def test_vap_loads_pinned_checkpoint_and_normalizes_lightning_keys(monkeypatch, wrapped):
    weights = {"encoder.weight": object(), "vap_head.weight": object()}
    checkpoint = weights
    if wrapped:
        checkpoint = {
            "state_dict": {f"net.{key}": value for key, value in weights.items()},
        }
        checkpoint["state_dict"]["net.VAP.codebook.emb.weight"] = object()

    def download(**kwargs):
        assert kwargs == {
            "repo_id": vap_adapter.DEFAULT_MODEL_ID,
            "filename": "oto.ckpt",
            "revision": vap_adapter.DEFAULT_REVISION,
        }
        return "oto.ckpt"

    def load(path, *, map_location, weights_only):
        assert (path, map_location, weights_only) == ("oto.ckpt", "cpu", True)
        return checkpoint

    class Model:
        def __init__(self, conf):
            pass

        def load_state_dict(self, state_dict):
            assert state_dict == weights

        def to(self, device):
            assert device == "cpu"
            return self

        def eval(self):
            return self

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        load=load,
        cuda=SimpleNamespace(is_available=lambda: False),
        serialization=SimpleNamespace(safe_globals=lambda _: nullcontext()),
    ))
    monkeypatch.setitem(sys.modules, "vap.model", SimpleNamespace(VapGPT=Model, VapConfig=object))
    monkeypatch.setitem(sys.modules, "vap.events", SimpleNamespace(EventConfig=object))
    monkeypatch.setattr("huggingface_hub.hf_hub_download", download)

    adapter = VAPAdapter()
    assert isinstance(adapter.model, Model)
    assert "oto.ckpt-silent-agent" in adapter.adapter_id
    assert vap_adapter.DEFAULT_REVISION in adapter.adapter_id


def test_vap_loads_checkpoint_with_serialized_configs(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    vap_model = pytest.importorskip("vap.model")
    vap_events = pytest.importorskip("vap.events")
    checkpoint_path = tmp_path / "oto.ckpt"
    torch.save({
        "state_dict": {"net.weight": torch.tensor([0.5])},
        "hyper_parameters": {
            "conf": vap_model.VapConfig(),
            "event_conf": vap_events.EventConfig(),
        },
    }, checkpoint_path)

    class Model(torch.nn.Module):
        def __init__(self, conf):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.zeros(1))

    monkeypatch.setattr(vap_model, "VapGPT", Model)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", lambda **_: str(checkpoint_path))
    adapter = VAPAdapter(device="cpu")

    assert adapter.model.weight.item() == 0.5
    assert adapter.model.training is False


def test_vap_predict_writes_causal_scores_and_model_metadata(tmp_path, monkeypatch, waveforms):
    import pandas as pd
    from datasets import Dataset

    from eot_harness.cli import _run_predict, build_parser

    row = {
        "id": "vap-turn",
        "language": "en",
        "audio": {"array": np.linspace(0, 1, 16_000).tolist(), "sampling_rate": 16_000},
        "silence_spans": [{"start": 0.1, "end": 0.2}, {"start": 0.3, "end": 0.5}],
    }
    monkeypatch.setattr("eot_harness.cli.load_hf_dataset", lambda *args, **kwargs: Dataset.from_list([row]))
    args = build_parser().parse_args([
        "predict", "--path", "test/vap", "--name", "en", "--split", "validation",
        "--adapter", "eot_harness.vap_adapter:VAPAdapter", "--batch-size", "2",
        "--output-dir", str(tmp_path),
    ])

    run_dir = _run_predict(args)[0]
    predictions = pd.read_parquet(run_dir / "predictions.parquet")
    assert predictions["label"].tolist() == ["hold", "hold", "eot", "eot", "eot"]
    assert predictions["timestamp"].tolist() == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5])
    assert [waveform.shape[-1] for waveform in waveforms] == [1600, 3200, 4800, 6400, 8000]
    np.testing.assert_allclose(predictions["p_eot"], [(n - 1) / 15_999 for n in [1600, 3200, 4800, 6400, 8000]])
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["display_name"] == "VAP (silent agent)"
    assert manifest["model"]["max_audio_sec"] == 20.0
    assert "score_point" not in manifest
