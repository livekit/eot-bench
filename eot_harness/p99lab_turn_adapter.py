from __future__ import annotations

import numpy as np

from .languages import supports_language_code
from .streaming_stt import SAMPLE_RATE, resample_audio

DEFAULT_TURN1_MODEL_ID = "p99lab/turn-1"
DEFAULT_TURN1_REVISION = "41f0273746c893187e687ef5a3e423830afbdd59"
DEFAULT_TURN1_MINI_MODEL_ID = "p99lab/turn-1-mini"
# v1.2.3. Later revisions of the repo add the v2.0.0 model.
DEFAULT_TURN1_MINI_REVISION = "22bcc75c9857d664ede4811cf3dfaa46be7c4376"
SUPPORTED_LANGUAGES = frozenset({"en"})


class P99LabTurn1Adapter:
    """Score causal user audio with p99lab turn-1.

    turn-1 averages two estimates built on two open speech encoders
    (Apache-2.0), which the `p99turn1` package downloads from their own
    repositories. It hears up to 8 seconds of recent audio and reads the last
    assistant message. It never reads the words of the turn under judgement.
    """

    display_name = "p99lab turn-1"

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_TURN1_MODEL_ID,
        revision: str | None = DEFAULT_TURN1_REVISION,
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
        revision: str | None = DEFAULT_TURN1_MINI_REVISION,
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
    return resample_audio(audio["array"], int(audio["sampling_rate"]), SAMPLE_RATE)


def _last_assistant_message(messages: list[dict]) -> str:
    for message in reversed(messages):
        if str(message.get("role", "")).strip() == "assistant":
            return str(message.get("content") or "").strip()
    return ""


# model_id is always passed to the packages, so their P99TURN1_WEIGHTS and
# P99TURN_WEIGHTS overrides cannot swap in weights that adapter_id does not name.
# Pass a local directory as model_id to run without downloads.
def _load_turn1(*, model_id: str, revision: str | None, device: str | None):
    from p99turn1 import Turn1

    return Turn1(model_id, revision=revision, device=device)


def _load_turn1_mini(*, model_id: str, revision: str | None, device: str | None):
    import torch
    from p99turn import Turn1Mini

    return Turn1Mini(model_id, revision=revision, device=device or ("cuda" if torch.cuda.is_available() else "cpu"))
