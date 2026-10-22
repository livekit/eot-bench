from __future__ import annotations

import numpy as np

from .languages import supports_any_benchmark_language

DEFAULT_AUDIO_MODEL_ID = "pipecat-ai/smart-turn-v3"
DEFAULT_AUDIO_MODEL_FILENAME = "smart-turn-v3.2-gpu.onnx"
HAAN_MODEL_ID = "CharanSripadi/haan"
HAAN_MODEL_FILENAME = "haan-telephony.onnx"


class SmartTurnAudioAdapter:
    display_name = "SmartTurn v3.2"
    score_point = 0.2

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_AUDIO_MODEL_ID,
        revision: str | None = None,
        audio_model_filename: str = DEFAULT_AUDIO_MODEL_FILENAME,
        sample_rate: int = 16000,
        chunk_length_sec: float = 8.0,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.audio_model_filename = audio_model_filename
        self.sample_rate = int(sample_rate)
        self.chunk_length_sec = float(chunk_length_sec)
        self.max_samples = int(self.chunk_length_sec * self.sample_rate)
        self.adapter_id = f"{model_id}-{audio_model_filename.replace('.onnx', '')}"
        if revision:
            self.adapter_id = f"{self.adapter_id}-{revision}"

        self.session = _load_smart_turn_session(
            model_id=model_id,
            audio_model_filename=audio_model_filename,
            revision=revision,
        )
        self.feature_extractor = _load_smart_turn_feature_extractor(chunk_length=self.chunk_length_sec)

    def supports_language(self, lang_code: str) -> bool:
        return supports_any_benchmark_language(lang_code)

    def predict_batch(self, batch):
        batch_features = []
        for item in batch:
            audio = item.get("audio") or {}
            arr = np.asarray(audio["array"], dtype=np.float32)
            sampling_rate = int(audio["sampling_rate"])
            if sampling_rate != self.sample_rate:
                arr = _resample_audio(arr, orig_freq=sampling_rate, new_freq=self.sample_rate)
            if len(arr) > self.max_samples:
                arr = arr[-self.max_samples :]
            elif len(arr) < self.max_samples:
                arr = np.pad(
                    arr,
                    (self.max_samples - len(arr), 0),
                    mode="constant",
                    constant_values=0,
                )
            feats = self.feature_extractor(
                arr,
                sampling_rate=self.sample_rate,
                return_tensors="np",
                padding="max_length",
                max_length=self.max_samples,
                truncation=True,
                do_normalize=True,
            )
            batch_features.append(feats.input_features[0])

        inputs = np.stack(batch_features).astype(np.float32)
        probs = self.session.run(None, {"input_features": inputs})[0].reshape(-1).tolist()
        return [float(prob) for prob in probs]


class HaanAudioAdapter(SmartTurnAudioAdapter):
    """haan: SmartTurn v3.2 fine-tuned with telephone-channel augmentation.

    Same architecture, preprocessing and ONNX interface as SmartTurn v3.2, so
    only the weights differ. See https://github.com/Charansripadi/haan.
    """

    display_name = "haan (SmartTurn v3.2 phone-audio fine-tune)"

    def __init__(
        self,
        *,
        model_id: str = HAAN_MODEL_ID,
        audio_model_filename: str = HAAN_MODEL_FILENAME,
        **kwargs,
    ) -> None:
        super().__init__(model_id=model_id, audio_model_filename=audio_model_filename, **kwargs)


def _load_smart_turn_session(*, model_id: str, audio_model_filename: str, revision: str | None):
    import torch  # Ensure bundled CUDA/cuDNN libs are loaded before ORT initializes.
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download

    del torch
    hf_download_kwargs = {"repo_id": model_id, "filename": audio_model_filename}
    if revision:
        hf_download_kwargs["revision"] = revision
    model_path = hf_hub_download(**hf_download_kwargs)

    sess_options = ort.SessionOptions()
    sess_options.log_severity_level = 3
    return ort.InferenceSession(
        model_path,
        sess_options=sess_options,
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )


def _load_smart_turn_feature_extractor(*, chunk_length: float):
    from transformers import WhisperFeatureExtractor

    return WhisperFeatureExtractor(chunk_length=chunk_length)


def _resample_audio(array: np.ndarray, *, orig_freq: int, new_freq: int) -> np.ndarray:
    import torch
    import torchaudio.functional as F

    return (
        F.resample(
            torch.from_numpy(np.asarray(array, dtype=np.float32)).unsqueeze(0),
            orig_freq=orig_freq,
            new_freq=new_freq,
        )
        .squeeze(0)
        .cpu()
        .numpy()
    )
