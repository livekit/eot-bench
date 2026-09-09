from __future__ import annotations

import math

import numpy as np

from .languages import supports_any_benchmark_language

DEFAULT_MODEL_ID = "viks66/VAP_checkpoints"
DEFAULT_REVISION = "b9aa0ba1718221153e04ef343c7f3b8cf84bfbc3"
SAMPLE_RATE = 16_000
FRAME_SAMPLES = 320


class VAPAdapter:
    """Score causal user audio with VAP's second speaker channel held silent."""

    display_name = "VAP (silent agent)"

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_MODEL_ID,
        revision: str | None = DEFAULT_REVISION,
        checkpoint_filename: str = "oto.ckpt",
        max_audio_sec: float = 20.0,
        device: str | None = None,
    ) -> None:
        self.max_audio_sec = float(max_audio_sec)
        if not math.isfinite(self.max_audio_sec) or self.max_audio_sec < FRAME_SAMPLES / SAMPLE_RATE:
            raise ValueError("VAP max_audio_sec must be finite and at least 0.02 seconds.")
        self.max_samples = int(self.max_audio_sec * SAMPLE_RATE)
        self.adapter_id = f"{model_id}/{checkpoint_filename}-silent-agent"
        if revision:
            self.adapter_id = f"{self.adapter_id}-{revision}"
        self.model = _load_vap_model(
            model_id=model_id,
            revision=revision,
            checkpoint_filename=checkpoint_filename,
            device=device,
        )

    def supports_language(self, lang_code: str) -> bool:
        return supports_any_benchmark_language(lang_code)

    def predict_batch(self, batch):
        scores = []
        for item in batch:
            audio = item["audio"]
            array = np.asarray(audio["array"], dtype=np.float32)
            sample_rate = int(audio["sampling_rate"])
            if array.ndim != 1:
                raise ValueError(f"VAP adapter expects mono audio, got shape={array.shape}")
            if sample_rate <= 0:
                raise ValueError("VAP audio sampling_rate must be positive.")
            array = array[-int(math.ceil(self.max_audio_sec * sample_rate)) :]
            if sample_rate != SAMPLE_RATE and array.size:
                array = _resample_audio(array, sample_rate=sample_rate)
            array = array[-self.max_samples :]
            # Pad only the past when the prefix is shorter than one model frame.
            if len(array) < FRAME_SAMPLES:
                array = np.pad(array, (FRAME_SAMPLES - len(array), 0))
            waveform = np.stack((array, np.zeros_like(array)))[None, ...]
            scores.append(_predict_eot(self.model, waveform))
        return scores


def _load_vap_model(*, model_id: str, revision: str | None, checkpoint_filename: str, device: str | None):
    import torch
    from huggingface_hub import hf_hub_download
    from vap.events import EventConfig
    from vap.model import VapConfig, VapGPT

    checkpoint_path = hf_hub_download(
        repo_id=model_id,
        filename=checkpoint_filename,
        revision=revision,
    )
    with torch.serialization.safe_globals([VapConfig, EventConfig]):
        state_dict = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if "state_dict" in state_dict:
        state_dict = {
            key.removeprefix("net."): value
            for key, value in state_dict["state_dict"].items()
            if "VAP.codebook" not in key
        }
    model = VapGPT(VapConfig())
    model.load_state_dict(state_dict)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    return model.to(device).eval()


def _predict_eot(model, waveform: np.ndarray) -> float:
    import torch

    device = next(model.parameters()).device
    with torch.inference_mode():
        output = model(torch.from_numpy(waveform).to(device))
        # VapGPT.probs also computes a training loss that needs future VAD frames.
        probs = output["logits"][:, -1:, :].softmax(dim=-1)
        p_now = model.objective.probs_next_speaker_aggregate(probs, from_bin=0, to_bin=1)
    return 1.0 - float(p_now[0, -1, 0].item())


def _resample_audio(array: np.ndarray, *, sample_rate: int) -> np.ndarray:
    import torch
    from torchaudio.functional import resample

    return resample(torch.from_numpy(array), sample_rate, SAMPLE_RATE).numpy()
