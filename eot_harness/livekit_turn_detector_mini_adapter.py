from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

from .languages import supports_any_benchmark_language
from .streaming_stt import SAMPLE_RATE, resample_audio

LIVEKIT_TURN_DETECTOR_MINI_MODEL_ID = "turn-detector-v1.1-mini"
LIVEKIT_TURN_DETECTOR_MINI_LOCAL_REVISION = "livekit-local-inference"
LIVEKIT_TURN_DETECTOR_MINI_AUDIO_SEC = 2.0
LIVEKIT_TURN_DETECTOR_MINI_WORKERS_ENV = "LIVEKIT_TURN_DETECTOR_MINI_WORKERS"
LIVEKIT_TURN_DETECTOR_MINI_MAX_DEFAULT_WORKERS = 8


class LiveKitTurnDetectorMiniAdapter:
    """Score the on-device LiveKit Turn Detector v1.1-mini via `livekit-local-inference`.

    The model reads the last 2.0 s of the turn plus the turn length so far
    (`turn_samples`), so the harness passes the whole causal prefix of the turn
    and the adapter crops the window itself.
    """

    display_name = "LiveKit Turn Detector v1.1-mini"
    score_point = 0.2

    def __init__(
        self,
        *,
        sample_rate: int = SAMPLE_RATE,
        audio_sec: float = LIVEKIT_TURN_DETECTOR_MINI_AUDIO_SEC,
        num_workers: int | None = None,
    ) -> None:
        self.model_id = LIVEKIT_TURN_DETECTOR_MINI_MODEL_ID
        self.revision = LIVEKIT_TURN_DETECTOR_MINI_LOCAL_REVISION
        self.sample_rate = int(sample_rate)
        self.audio_sec = float(audio_sec)
        # None makes the harness pass the full prefix, so `turn_samples` sees the whole turn.
        self.max_audio_sec = None
        self.max_samples = int(round(self.sample_rate * self.audio_sec))
        self.num_workers = _resolve_num_workers(num_workers)
        self._thread_local = threading.local()
        self._models: list[Any] = []
        self._models_lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None
        self.adapter_id = f"livekit/{self.model_id}-{self.revision}"
        self.model = _load_local_eot_model() if self.num_workers == 1 else None
        if self.num_workers > 1:
            self._executor = ThreadPoolExecutor(
                max_workers=self.num_workers,
                thread_name_prefix="lk-turn-detector-mini",
            )

    def predict_batch(self, batch):
        if self._executor is None:
            return [self._predict_item(item) for item in batch]
        return list(self._executor.map(self._predict_item, batch))

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None
        for model in self._models:
            close = getattr(model, "close", None)
            if callable(close):
                close()
        self._models.clear()
        if self.model is not None:
            close = getattr(self.model, "close", None)
            if callable(close):
                close()
            self.model = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def supports_language(self, lang_code: str) -> bool:
        return supports_any_benchmark_language(lang_code)

    def _predict_item(self, item: dict[str, Any]) -> float:
        pcm, turn_samples = _prepare_pcm16_tail(
            item,
            sample_rate=self.sample_rate,
            max_samples=self.max_samples,
        )
        return float(self._worker_model().predict(pcm, turn_samples=turn_samples))

    def _worker_model(self):
        if self.model is not None:
            return self.model
        model = getattr(self._thread_local, "model", None)
        if model is None:
            model = _load_local_eot_model()
            self._thread_local.model = model
            with self._models_lock:
                self._models.append(model)
        return model


def _resolve_num_workers(num_workers: int | None) -> int:
    if num_workers is None:
        env_value = os.getenv(LIVEKIT_TURN_DETECTOR_MINI_WORKERS_ENV)
        if env_value is not None and env_value.strip():
            num_workers = int(env_value)
    if num_workers is None:
        cpu_count = os.cpu_count() or 1
        num_workers = min(LIVEKIT_TURN_DETECTOR_MINI_MAX_DEFAULT_WORKERS, max(1, cpu_count))
    value = int(num_workers)
    if value <= 0:
        raise ValueError("LiveKit Turn Detector mini num_workers must be positive.")
    return value


def _prepare_pcm16_tail(
    item: dict[str, Any], *, sample_rate: int, max_samples: int
) -> tuple[np.ndarray, int]:
    """Return the last `max_samples` of the audio as PCM16 and the full audio length in samples."""
    audio = item.get("audio") or {}
    arr = np.asarray(audio["array"], dtype=np.float32)
    if arr.ndim == 2:
        arr = arr.mean(axis=1)
    elif arr.ndim != 1:
        raise ValueError(f"LiveKit Turn Detector mini adapter expects mono audio, got shape={arr.shape}")

    input_sample_rate = int(audio["sampling_rate"])
    if input_sample_rate != sample_rate:
        arr = resample_audio(arr, input_sample_rate, sample_rate)

    total_samples = int(arr.size)
    if max_samples > 0:
        arr = arr[-max_samples:]
    elif max_samples == 0:
        arr = arr[:0]
    return _float_audio_to_pcm16(arr), total_samples


def _float_audio_to_pcm16(array: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(array, dtype=np.float32), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    return np.ascontiguousarray(pcm)


def _load_local_eot_model():
    try:
        from livekit.local_inference import EOT, EOT_MAX_SAMPLES
    except ImportError as exc:
        raise RuntimeError(
            "LiveKit Turn Detector mini requires `livekit-local-inference` "
            "(installed by `livekit-agents>=1.6.0rc1`)."
        ) from exc
    # Older releases bundle v1-mini, whose window is 1.2 s.
    expected = int(round(SAMPLE_RATE * LIVEKIT_TURN_DETECTOR_MINI_AUDIO_SEC))
    if EOT_MAX_SAMPLES != expected:
        raise RuntimeError(
            f"The installed `livekit-local-inference` has a {EOT_MAX_SAMPLES}-sample EOT window. "
            f"LiveKit Turn Detector v1.1-mini needs {expected} samples ({LIVEKIT_TURN_DETECTOR_MINI_AUDIO_SEC:g} s); "
            "install a release that bundles v1.1-mini."
        )
    return EOT()
