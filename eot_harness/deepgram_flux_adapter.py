from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.parse import urlencode

import numpy as np

from .io import DEFAULT_INFERENCE_INTERVAL, DEFAULT_MIN_SILENCE, _time_grid, decode_audio, span_label
from .languages import normalize_language_code, supports_language_code

FLUX_MULTI_SUPPORTED_LANGUAGES = {"en", "es", "fr", "de", "hi", "ru", "pt", "ja", "it", "nl"}
FLUX_EN_SUPPORTED_LANGUAGES = {"en"}
SAMPLE_RATE = 16000
DEFAULT_CHUNK_MS = 100
DEFAULT_CONCURRENCY = 4
DEFAULT_EOT_THRESHOLD = 0.7
DEFAULT_MAX_RETRIES = 3
_EPS = 1e-6


class DeepgramFluxStreamingAdapter:
    """Replay full turns through Deepgram Flux and convert TurnInfo events to span scores."""

    display_name = "Deepgram Flux"
    def __init__(
        self,
        *,
        model: str = "flux-general-en",
        chunk_ms: int = DEFAULT_CHUNK_MS,
        eot_threshold: float = DEFAULT_EOT_THRESHOLD,
        concurrency: int = DEFAULT_CONCURRENCY,
        skip_unsupported_languages: bool = False,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        if not model:
            raise ValueError("model must be a non-empty string")
        if chunk_ms <= 0:
            raise ValueError("chunk_ms must be positive")
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        if not 0.0 <= eot_threshold <= 1.0:
            raise ValueError("eot_threshold must be in [0, 1]")

        self.model = model
        self.chunk_ms = int(chunk_ms)
        self.eot_threshold = float(eot_threshold)
        self.concurrency = int(concurrency)
        self.skip_unsupported_languages = bool(skip_unsupported_languages)
        self.max_retries = int(max_retries)

    @property
    def adapter_id(self) -> str:
        return f"deepgram/{self.model}"

    def supports_language(self, lang_code: str) -> bool:
        if self.model == "flux-general-en":
            return supports_language_code(lang_code, FLUX_EN_SUPPORTED_LANGUAGES)
        if self.model == "flux-general-multi":
            return supports_language_code(lang_code, FLUX_MULTI_SUPPORTED_LANGUAGES)
        return supports_language_code(lang_code, FLUX_EN_SUPPORTED_LANGUAGES)

    async def predict_turn(
        self,
        row: dict[str, Any],
        *,
        inference_interval: float = DEFAULT_INFERENCE_INTERVAL,
    ) -> dict[str, Any]:
        language_hint, skip_row = self._language_hint_or_skip(row)
        if skip_row is not None:
            return skip_row

        api_key = _resolve_deepgram_api_key()
        # Under load Flux sometimes does not close the stream. Each attempt opens
        # a new connection, so it is safe to replay the turn.
        for attempt in range(self.max_retries + 1):
            try:
                return await self._replay_turn(
                    row,
                    api_key,
                    inference_interval=inference_interval,
                    language_hint=language_hint,
                )
            except _FluxCloseTimeout:
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(float(attempt + 1))
        raise AssertionError("unreachable")

    def _language_hint_or_skip(self, row: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
        if "language" not in row:
            raise RuntimeError("Deepgram Flux requires a `language` column in each dataset row.")

        language = normalize_language_code(row["language"])
        if self.supports_language(language):
            if self.model == "flux-general-multi":
                return language, None
            return None, None
        if self.model == "flux-general-multi" and self.skip_unsupported_languages:
            return None, {
                "id": row.get("id"),
                "skipped": True,
                "language": language,
                "reason": "unsupported_language",
                "events": [],
                "prediction_rows": [],
                "audio_sec": 0.0,
            }
        if self.model == "flux-general-en":
            supported = sorted(FLUX_EN_SUPPORTED_LANGUAGES)
        elif self.model == "flux-general-multi":
            supported = sorted(FLUX_MULTI_SUPPORTED_LANGUAGES)
        else:
            supported = sorted(FLUX_EN_SUPPORTED_LANGUAGES)
        raise RuntimeError(
            f"Unsupported language for {self.model} on row {row.get('id')!r}: {language!r}. "
            f"Supported languages: {supported}",
        )

    async def _replay_turn(
        self,
        row: dict[str, Any],
        api_key: str,
        *,
        inference_interval: float,
        language_hint: str | None,
    ) -> dict[str, Any]:
        websockets = _import_websockets()
        audio_array, sample_rate = decode_audio(row["audio"])
        audio_array = _resample_audio(audio_array, sample_rate, SAMPLE_RATE)
        audio_bytes = _pcm16le_bytes(audio_array)
        total_audio_sec = float(len(audio_array) / SAMPLE_RATE)

        params = {
            "model": self.model,
            "encoding": "linear16",
            "sample_rate": str(SAMPLE_RATE),
            "eot_threshold": str(self.eot_threshold),
        }
        if language_hint is not None:
            params["language_hint"] = language_hint
        url = f"wss://api.deepgram.com/v2/listen?{urlencode(params)}"

        events: list[dict[str, Any]] = []
        chunk_size = int(SAMPLE_RATE * (self.chunk_ms / 1000.0) * 2)
        if chunk_size <= 0:
            raise RuntimeError(f"Invalid Flux chunk size from chunk_ms={self.chunk_ms}.")

        async with websockets.connect(
            url,
            additional_headers={"Authorization": f"Token {api_key}"},
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            recv_task = asyncio.create_task(_recv_flux_events(ws, row_id=row["id"], events=events))
            for start in range(0, len(audio_bytes), chunk_size):
                await ws.send(audio_bytes[start : start + chunk_size])
                await asyncio.sleep(self.chunk_ms / 1000.0)
            await ws.send(json.dumps({"type": "CloseStream"}))
            try:
                await asyncio.wait_for(recv_task, timeout=15.0)
            except asyncio.TimeoutError as exc:
                recv_task.cancel()
                raise _FluxCloseTimeout(f"Timed out waiting for Flux close on {row['id']!r}.") from exc

        if not events:
            raise RuntimeError(f"No TurnInfo events received for row {row['id']!r}.")

        return {
            "id": row["id"],
            "audio_sec": total_audio_sec,
            "events": events,
            "prediction_rows": build_flux_prediction_rows(
                row,
                events,
                inference_interval=inference_interval,
            ),
        }


class _FluxCloseTimeout(RuntimeError):
    """Flux did not close the stream after `CloseStream`."""


async def _recv_flux_events(ws, *, row_id: Any, events: list[dict[str, Any]]) -> None:
    async for message in ws:
        data = json.loads(message)
        msg_type = data.get("type")
        if msg_type == "Error":
            raise RuntimeError(f"Deepgram error for row {row_id!r}: {data}")
        if msg_type != "TurnInfo":
            continue
        event_name = data.get("event")
        if event_name is None:
            raise RuntimeError(f"Missing event in TurnInfo for row {row_id!r}: {data}")
        events.append(
            {
                "event": event_name,
                "audio_window_start": data.get("audio_window_start"),
                "audio_window_end": data.get("audio_window_end"),
                "end_of_turn_confidence": data.get("end_of_turn_confidence"),
                "turn_index": data.get("turn_index"),
            },
        )


def build_flux_prediction_rows(
    row: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    inference_interval: float,
) -> list[dict[str, Any]]:
    usable_events = sorted(
        [
            {
                "audio_window_end": float(event["audio_window_end"]),
                "end_of_turn_confidence": float(event["end_of_turn_confidence"]),
            }
            for event in events
            if event.get("audio_window_end") is not None
            and event.get("end_of_turn_confidence") is not None
        ],
        key=lambda event: event["audio_window_end"],
    )
    if not usable_events:
        raise RuntimeError(f"No usable Flux confidence events for row {row.get('id')!r}.")

    rows: list[dict[str, Any]] = []
    event_idx = 0
    current_score = 0.0
    silence_spans = row["silence_spans"]

    for span_index, span in enumerate(silence_spans):
        start = float(span["start"])
        end = float(span["end"])
        if end - start < DEFAULT_MIN_SILENCE - _EPS:
            continue
        label = span_label(silence_spans, span_index)
        for timestamp in _time_grid(start, end, inference_interval):
            while event_idx < len(usable_events) and usable_events[event_idx]["audio_window_end"] <= timestamp + _EPS:
                current_score = usable_events[event_idx]["end_of_turn_confidence"]
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


def _resolve_deepgram_api_key() -> str:
    api_key = str(os.getenv("DEEPGRAM_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("DEEPGRAM_API_KEY must be set in eot_harness/.env.")
    return api_key


def _resample_audio(array: np.ndarray, orig_sr: int, new_sr: int) -> np.ndarray:
    audio = np.asarray(array, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if orig_sr == new_sr:
        return audio

    try:
        import librosa
    except ImportError as exc:
        raise RuntimeError("Deepgram Flux adapter requires `librosa` to resample non-16kHz audio.") from exc

    return np.asarray(librosa.resample(audio, orig_sr=orig_sr, target_sr=new_sr), dtype=np.float32)


def _pcm16le_bytes(array: np.ndarray) -> bytes:
    clipped = np.clip(np.asarray(array, dtype=np.float32), -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def _import_websockets():
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("Deepgram Flux adapter requires the `websockets` package.") from exc
    return websockets
