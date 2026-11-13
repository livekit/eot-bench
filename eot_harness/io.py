from __future__ import annotations

import io
import math
from collections.abc import Iterator
from typing import Any

import numpy as np
import soundfile as sf

from .schemas import PREDICTION_LABELS

DEFAULT_TRANSCRIPT_LAG = 0.5
DEFAULT_INFERENCE_INTERVAL = 0.1
DEFAULT_MIN_SILENCE = 0.1
_EPS = 1e-6


def load_hf_dataset(
    path: str,
    name: str | None,
    split: str,
    *,
    revision: str | None = None,
    token: str | None = None,
):
    from datasets import Audio, load_dataset

    ds = load_dataset(path, name, split=split, revision=revision, token=token)
    return ds.cast_column("audio", Audio(decode=False))


def span_label(silence_spans: list[dict], span_index: int) -> str:
    """Return the `hold`/`eot` label of one silence span.

    A span's own `label` wins. Without one, the last span of the row is the end
    of the turn and every earlier span is a mid-turn pause.
    """
    label = silence_spans[span_index].get("label")
    if label is None:
        return "eot" if span_index == len(silence_spans) - 1 else "hold"
    if label not in PREDICTION_LABELS:
        raise ValueError(f"Silence span label must be one of {PREDICTION_LABELS}, got {label!r}.")
    return label


def build_messages(
    row: dict,
    timestamp: float,
    *,
    transcript_lag: float = DEFAULT_TRANSCRIPT_LAG,
) -> list[dict[str, str]]:
    messages = [dict(message) for message in (row.get("messages") or [])]

    words = row.get("words") or []
    if words:
        effective_time = float(timestamp) - float(transcript_lag)
        visible_words = [str(word["word"]).strip() for word in words if float(word["end"]) <= effective_time + _EPS]
        visible_words = [word for word in visible_words if word]
        if visible_words:
            messages.append({"role": "user", "content": " ".join(visible_words)})

    return messages


def transform_row(
    row: dict,
    *,
    inference_interval: float = DEFAULT_INFERENCE_INTERVAL,
    transcript_lag: float = DEFAULT_TRANSCRIPT_LAG,
    min_silence_span: float = DEFAULT_MIN_SILENCE,
) -> list[dict[str, Any]]:
    return list(
        iter_transformed_row(
            row,
            inference_interval=inference_interval,
            transcript_lag=transcript_lag,
            min_silence_span=min_silence_span,
        )
    )


def iter_transformed_row(
    row: dict,
    *,
    inference_interval: float = DEFAULT_INFERENCE_INTERVAL,
    transcript_lag: float = DEFAULT_TRANSCRIPT_LAG,
    min_silence_span: float = DEFAULT_MIN_SILENCE,
    max_audio_sec: float | None = None,
) -> Iterator[dict[str, Any]]:
    array, sample_rate = decode_audio(row["audio"])
    language = _row_language(row)
    silence_spans = row["silence_spans"]
    max_audio_samples = _max_audio_samples(max_audio_sec, sample_rate=sample_rate)

    for span_index, span in enumerate(silence_spans):
        start = float(span["start"])
        end = float(span["end"])
        if end - start < min_silence_span - _EPS:
            continue
        label = span_label(silence_spans, span_index)
        for timestamp in _time_grid(start, end, inference_interval):
            end_sample = int(math.floor(float(timestamp) * sample_rate + _EPS))
            start_sample = 0
            if max_audio_samples is not None:
                start_sample = max(0, end_sample - max_audio_samples)
            yield {
                "id": row["id"],
                "language": language,
                "span_index": span_index,
                "timestamp": timestamp,
                "silence_dur": round(timestamp - start, 6),
                "label": label,
                "audio": {
                    "array": array[start_sample:end_sample].copy(),
                    "sampling_rate": sample_rate,
                },
                "messages": build_messages(row, timestamp, transcript_lag=transcript_lag),
            }


def iter_batches(
    ds,
    *,
    batch_size: int,
    inference_interval: float = DEFAULT_INFERENCE_INTERVAL,
    transcript_lag: float = DEFAULT_TRANSCRIPT_LAG,
    min_silence_span: float = DEFAULT_MIN_SILENCE,
    max_audio_sec: float | None = None,
) -> Iterator[tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
    """Yield metadata rows and matching adapter batch inputs."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    batch_meta: list[dict[str, Any]] = []
    batch_inputs: list[dict[str, Any]] = []

    for row in ds:
        for example in iter_transformed_row(
            row,
            inference_interval=inference_interval,
            transcript_lag=transcript_lag,
            min_silence_span=min_silence_span,
            max_audio_sec=max_audio_sec,
        ):
            batch_meta.append(
                {
                    "id": example["id"],
                    "language": example["language"],
                    "span_index": example["span_index"],
                    "timestamp": example["timestamp"],
                    "silence_dur": example["silence_dur"],
                    "label": example["label"],
                },
            )
            batch_inputs.append(
                {
                    "language": example["language"],
                    "audio": example["audio"],
                    "messages": example["messages"],
                },
            )
            if len(batch_inputs) == batch_size:
                yield batch_meta, batch_inputs
                batch_meta = []
                batch_inputs = []

    if batch_inputs:
        yield batch_meta, batch_inputs


def _max_audio_samples(max_audio_sec: float | None, *, sample_rate: int) -> int | None:
    if max_audio_sec is None:
        return None
    value = float(max_audio_sec)
    if value <= 0:
        raise ValueError("max_audio_sec must be positive")
    return int(math.ceil(value * sample_rate - _EPS))


def build_span_set(ds, *, min_silence_span: float = DEFAULT_MIN_SILENCE) -> list[dict[str, Any]]:
    """Return the dataset-level span set addressed by prediction artifacts."""
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for row in ds:
        row_id = str(row["id"])
        language = _row_language(row)
        if row_id in seen_ids:
            raise ValueError(f"Duplicate id in dataset: {row_id}")
        seen_ids.add(row_id)

        silence_spans = row["silence_spans"]
        for span_index, span in enumerate(silence_spans):
            start = float(span["start"])
            end = float(span["end"])
            duration = end - start
            if duration < min_silence_span - _EPS:
                continue
            span_row = {
                "id": row_id,
                "language": language,
                "span_index": span_index,
                "label": span_label(silence_spans, span_index),
                "start": round(start, 6),
                "end": round(end, 6),
                "duration": round(duration, 6),
            }
            if row.get("cohort") is not None:
                span_row["cohort"] = str(row["cohort"])
            rows.append(span_row)

    return rows


def _row_language(row: dict) -> str:
    language = row.get("language")
    if language is None:
        row_id = row.get("id", "<unknown>")
        raise ValueError(f"Dataset row {row_id!r} is missing required `language`.")
    value = str(language).strip().lower()
    if not value:
        row_id = row.get("id", "<unknown>")
        raise ValueError(f"Dataset row {row_id!r} has empty `language`.")
    return value


def _time_grid(start: float, end: float, step: float) -> list[float]:
    n_steps = max(0, int(math.floor((end - start) / step + _EPS)))
    values = [round(start + i * step, 6) for i in range(n_steps + 1)]
    if values and values[-1] < end - _EPS:
        values.append(round(end, 6))
    elif not values:
        values = [round(start, 6), round(end, 6)]
    return values


def decode_audio(audio: dict) -> tuple[np.ndarray, int]:
    if "array" in audio and "sampling_rate" in audio:
        return np.asarray(audio["array"]), int(audio["sampling_rate"])

    audio_bytes = audio.get("bytes")
    if audio_bytes is None:
        raise ValueError("Audio must contain either decoded `array`/`sampling_rate` or encoded `bytes`.")

    array, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    if array.ndim > 1:
        array = array.mean(axis=1)
    return np.asarray(array, dtype=np.float32), int(sample_rate)
