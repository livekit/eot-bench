from __future__ import annotations

import numpy as np

from .languages import supports_language_code

DEFAULT_TURN1_MODEL_ID = "p99lab/turn-1"
DEFAULT_TURN1_MINI_MODEL_ID = "p99lab/turn-1-mini"
SUPPORTED_LANGUAGES = frozenset({"en"})
SAMPLE_RATE = 16_000


class P99LabTurn1Adapter:
    """Score causal user audio with p99lab turn-1.

    turn-1 averages two estimates built on two open speech encoders
    (Apache-2.0), which the `p99turn1` package downloads from their own
    repositories. It hears up to
    8 seconds of recent audio and reads the last assistant message. It never
    reads the words of the turn under judgement.
    """

    display_name = "p99lab turn-1"

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_TURN1_MODEL_ID,
        revision: str | None = None,
        max_audio_sec: float = 8.0,
        device: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.max_audio_sec = float(max_audio_sec)
        self.adapter_id = f"{model_id}-{revision}" if revision else model_id
        self.model = _load_turn1(model_id=model_id, revision=revision, device=device)

    def supports_language(self, lang_code: str) -> bool:
        return supports_language_code(lang_code, SUPPORTED_LANGUAGES)

    def predict_batch(self, batch):
        if not batch:
            return []
        windows = [_mono_16k(item["audio"]) for item in batch]
        contexts = [_last_assistant_message(item.get("messages") or []) for item in batch]
        # The model splits the batch itself: 16 windows per pass on the 1.7B
        # backbone and 32 on the 0.6B one.
        return [float(score) for score in self.model.score_windows(windows, contexts)]


class P99LabTurn1MiniAdapter:
    """Score causal user audio with p99lab turn-1-mini, a 5.3M-parameter audio-only streaming model."""

    display_name = "p99lab turn-1-mini"

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_TURN1_MINI_MODEL_ID,
        revision: str | None = None,
        max_audio_sec: float = 40.0,
        device: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.max_audio_sec = float(max_audio_sec)
        self.adapter_id = f"{model_id}-{revision}" if revision else model_id
        self.model = _load_turn1_mini(model_id=model_id, revision=revision, device=device)

    def supports_language(self, lang_code: str) -> bool:
        return supports_language_code(lang_code, SUPPORTED_LANGUAGES)

    def predict_batch(self, batch):
        # Each prefix is scored on its own from a zero state, so other items in
        # the batch do not change its score. Text history is ignored.
        return [float(self.model.score(_mono_16k(item["audio"]))) for item in batch]


def _mono_16k(audio: dict) -> np.ndarray:
    array = np.asarray(audio["array"], dtype=np.float32)
    sample_rate = int(audio["sampling_rate"])
    if array.ndim > 1:
        array = array.mean(axis=-1)
    if sample_rate != SAMPLE_RATE and array.size:
        array = _resample_audio(array, sample_rate=sample_rate)
    return array


def _last_assistant_message(messages: list[dict]) -> str:
    for message in reversed(messages):
        if str(message.get("role", "")).strip() == "assistant":
            return str(message.get("content") or "").strip()
    return ""


def _load_turn1(*, model_id: str, revision: str | None, device: str | None):
    from p99turn1 import Turn1

    # With the default repo id the package resolves the weights itself, so a
    # local directory in P99TURN1_WEIGHTS can stand in for the download.
    weights = None if model_id == DEFAULT_TURN1_MODEL_ID else model_id
    return Turn1(weights, revision=revision, device=device)


def _load_turn1_mini(*, model_id: str, revision: str | None, device: str | None):
    import torch
    from p99turn import Turn1Mini

    # As above: P99TURN_WEIGHTS can point at a local directory.
    weights = None if model_id == DEFAULT_TURN1_MINI_MODEL_ID else model_id
    return Turn1Mini(weights, revision=revision, device=device or ("cuda" if torch.cuda.is_available() else "cpu"))


def _resample_audio(array: np.ndarray, *, sample_rate: int) -> np.ndarray:
    import torch
    import torchaudio.functional as F

    return (
        F.resample(
            torch.from_numpy(np.asarray(array, dtype=np.float32)).unsqueeze(0),
            orig_freq=sample_rate,
            new_freq=SAMPLE_RATE,
        )
        .squeeze(0)
        .cpu()
        .numpy()
    )
