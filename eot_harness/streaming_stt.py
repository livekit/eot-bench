from __future__ import annotations

import os
from typing import Any

import numpy as np

from .io import DEFAULT_INFERENCE_INTERVAL, DEFAULT_MIN_SILENCE, _time_grid, decode_audio, span_label

SAMPLE_RATE = 16000
DEFAULT_CHUNK_MS = 100
_EPS = 1e-6


def prepare_pcm16_audio(row: dict[str, Any], *, sample_rate: int = SAMPLE_RATE) -> tuple[bytes, float]:
    audio_array, original_sample_rate = decode_audio(row["audio"])
    audio_array = resample_audio(audio_array, original_sample_rate, sample_rate)
    return pcm16le_bytes(audio_array), float(len(audio_array) / sample_rate)


def resample_audio(array: np.ndarray, orig_sr: int, new_sr: int) -> np.ndarray:
    audio = np.asarray(array, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if orig_sr == new_sr:
        return audio

    try:
        import librosa
    except ImportError as exc:
        raise RuntimeError("Streaming STT adapters require `librosa` to resample non-16kHz audio.") from exc

    return np.asarray(librosa.resample(audio, orig_sr=orig_sr, target_sr=new_sr), dtype=np.float32)


def pcm16le_bytes(array: np.ndarray) -> bytes:
    clipped = np.clip(np.asarray(array, dtype=np.float32), -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def chunk_size_bytes(*, sample_rate: int, chunk_ms: int, bytes_per_sample: int = 2) -> int:
    chunk_size = int(sample_rate * (chunk_ms / 1000.0) * bytes_per_sample)
    if chunk_size <= 0:
        raise RuntimeError(f"Invalid streaming chunk size from chunk_ms={chunk_ms}.")
    return chunk_size


def build_event_prediction_rows(
    row: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    inference_interval: float = DEFAULT_INFERENCE_INTERVAL,
) -> list[dict[str, Any]]:
    usable_events = sorted(
        [
            {
                "timestamp": float(event["timestamp"]),
                "p_eot": float(event["p_eot"]),
            }
            for event in events
            if event.get("timestamp") is not None and event.get("p_eot") is not None
        ],
        key=lambda event: event["timestamp"],
    )

    rows: list[dict[str, Any]] = []
    silence_spans = row["silence_spans"]

    for span_index, span in enumerate(silence_spans):
        start = float(span["start"])
        end = float(span["end"])
        if end - start < DEFAULT_MIN_SILENCE - _EPS:
            continue
        label = span_label(silence_spans, span_index)
        span_events = [
            event for event in usable_events
            if start - _EPS <= event["timestamp"] <= end + _EPS
        ]
        event_idx = 0
        current_score = 0.0
        for timestamp in _time_grid(start, end, inference_interval):
            while event_idx < len(span_events) and span_events[event_idx]["timestamp"] <= timestamp + _EPS:
                current_score = span_events[event_idx]["p_eot"]
                event_idx += 1
            rows.append(
                {
                    "id": row["id"],
                    "span_index": span_index,
                    "timestamp": float(timestamp),
                    "silence_dur": round(float(timestamp - start), 6),
                    "p_eot": float(current_score),
                    "label": label,
                },
            )
    if not rows:
        raise RuntimeError(f"No prediction rows generated for row {row.get('id')!r}.")
    return rows


def resolve_api_key(env_var: str, *aliases: str) -> str:
    names = (env_var, *aliases)
    for name in names:
        api_key = str(os.getenv(name) or "").strip()
        if api_key:
            return api_key
    if aliases:
        raise RuntimeError(f"One of {', '.join(names)} must be set in eot_harness/.env.")
    raise RuntimeError(f"{env_var} must be set in eot_harness/.env.")


def import_websockets():
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("Streaming STT adapters require the `websockets` package.") from exc
    return websockets
