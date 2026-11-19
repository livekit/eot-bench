from __future__ import annotations

from typing import Any

from .io import DEFAULT_INFERENCE_INTERVAL, decode_audio
from .languages import supports_any_benchmark_language
from .streaming_stt import SAMPLE_RATE, build_event_prediction_rows, resample_audio

DEFAULT_MODEL_ID = "inworld/sava"
DEFAULT_WEIGHTS_FILENAME = "sava.safetensors"
# The revision that inworld-sava 1.0.0 registers for `inworld/sava`.
DEFAULT_REVISION = "1beae7c1dd0df6b0f92030644fc905eb087dc6a0"
FRAME_SEC = 0.04


class InworldSavaAdapter:
    """Score user audio with Inworld SAVA, a 25.5M-parameter audio-only streaming model.

    One causal pass per turn gives an end-of-turn probability for each whole
    40 ms frame. The score at a prediction timestamp is the probability of the
    last frame that ends at or before it, so it uses no later audio.
    """

    display_name = "Inworld SAVA"
    concurrency = 1

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_MODEL_ID,
        revision: str | None = DEFAULT_REVISION,
        device: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.adapter_id = f"{model_id}-{revision}" if revision else model_id
        # Not `model`: the harness writes that attribute of a streaming adapter to the manifest.
        self._sava_model = _load_sava(model_id=model_id, revision=revision, device=device)

    def supports_language(self, lang_code: str) -> bool:
        return supports_any_benchmark_language(lang_code)

    def predict_turn(
        self,
        row: dict[str, Any],
        *,
        inference_interval: float = DEFAULT_INFERENCE_INTERVAL,
    ) -> dict[str, Any]:
        array, sample_rate = decode_audio(row["audio"])
        samples = resample_audio(array, sample_rate, SAMPLE_RATE)
        scores = _frame_scores(self._sava_model, samples)
        events = [
            {"timestamp": round((index + 1) * FRAME_SEC, 6), "p_eot": float(score)}
            for index, score in enumerate(scores)
        ]
        return {
            "id": row["id"],
            "audio_sec": float(len(samples) / SAMPLE_RATE),
            "events": events,
            "prediction_rows": build_event_prediction_rows(
                row,
                events + _span_start_events(row, scores),
                inference_interval=inference_interval,
            ),
        }


def _span_start_events(row: dict[str, Any], scores) -> list[dict[str, float]]:
    """Repeat at each span start the score that the model held at that time.

    The harness reads only the events inside a span and starts each span at
    0.0. Without these events, the first prediction of a span would lose the
    score of the frame that ended just before the span.
    """
    events = []
    for span in row["silence_spans"]:
        start = float(span["start"])
        n_frames = min(int((start + 1e-6) / FRAME_SEC), len(scores))
        if n_frames:
            events.append({"timestamp": start, "p_eot": float(scores[n_frames - 1])})
    return events


def _frame_scores(model, samples):
    from inworld import sava

    # `push` steps whole frames only. A trailing partial frame is never padded
    # with silence, which the model could read as a pause.
    return sava.Session(model).push(samples).turn


# Pass a local weights file as model_id with revision=None to run without downloads.
def _load_sava(*, model_id: str, revision: str | None, device: str | None):
    import torch
    from inworld import sava

    source = f"hf://{model_id}/{DEFAULT_WEIGHTS_FILENAME}@{revision}" if revision else model_id
    return sava.load(source, device or ("cuda" if torch.cuda.is_available() else "cpu"))
