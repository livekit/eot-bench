from __future__ import annotations

import asyncio
import json
from typing import Any

from .io import DEFAULT_INFERENCE_INTERVAL
from .languages import row_language, supports_any_benchmark_language
from .streaming_stt import (
    build_event_prediction_rows,
    chunk_size_bytes,
    prepare_pcm16_audio,
    resolve_api_key,
)

DEFAULT_GRADIUM_URL = "https://api.gradium.ai/api"
DEFAULT_GRADIUM_MODEL = "default"
DEFAULT_CONCURRENCY = 4
DEFAULT_EOT_THRESHOLD = 0.5
SAMPLE_RATE = 24000
# Gradium streaming STT emits one VAD `step` message per 80ms of processed audio.
VAD_STEP_S = 0.08
DEFAULT_CHUNK_MS = 80
VAD_INACTIVITY_INDEX = 3
# Languages the Gradium ASR worker accepts in json_config; other benchmark
# languages run without a language hint rather than erroring the session.
GRADIUM_LANGUAGES = frozenset({"en", "fr", "de", "es", "pt"})


class GradiumStreamingAdapter:
    """Replay full turns through Gradium streaming STT and score VAD inactivity steps."""

    display_name = "Gradium"
    def __init__(
        self,
        *,
        model: str = DEFAULT_GRADIUM_MODEL,
        chunk_ms: int = DEFAULT_CHUNK_MS,
        eot_threshold: float = DEFAULT_EOT_THRESHOLD,
        concurrency: int = DEFAULT_CONCURRENCY,
        url: str | None = None,
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
        self.url = str(url or DEFAULT_GRADIUM_URL)

    @property
    def adapter_id(self) -> str:
        return f"gradium/{self.model}"

    def supports_language(self, lang_code: str) -> bool:
        return supports_any_benchmark_language(lang_code)

    async def predict_turn(
        self,
        row: dict[str, Any],
        *,
        inference_interval: float = DEFAULT_INFERENCE_INTERVAL,
    ) -> dict[str, Any]:
        gradium_client = _import_gradium_client()
        api_key = resolve_api_key("GRADIUM_API_KEY")
        audio_bytes, total_audio_sec = prepare_pcm16_audio(row, sample_rate=SAMPLE_RATE)
        chunk_size = chunk_size_bytes(sample_rate=SAMPLE_RATE, chunk_ms=self.chunk_ms)

        async def audio_gen():
            for start in range(0, len(audio_bytes), chunk_size):
                yield audio_bytes[start : start + chunk_size]

        client = gradium_client.GradiumClient(base_url=self.url, api_key=api_key)
        events: list[dict[str, Any]] = []
        timeout = 60.0 + 2.0 * total_audio_sec
        try:
            await asyncio.wait_for(
                self._collect_events(client, audio_gen(), events, language=row_language(row)),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError(f"Timed out waiting for Gradium stream on {row['id']!r}.") from exc

        if not events:
            raise RuntimeError(f"No VAD step events received for row {row['id']!r}.")

        return {
            "id": row["id"],
            "audio_sec": total_audio_sec,
            "events": events,
            "prediction_rows": build_event_prediction_rows(
                row,
                events,
                inference_interval=inference_interval,
            ),
        }

    async def _collect_events(
        self, client, audio_gen, events: list[dict[str, Any]], *, language: str | None = None
    ) -> None:
        setup = {
            "model_name": self.model,
            "input_format": "pcm",
        }
        if language in GRADIUM_LANGUAGES:
            setup["json_config"] = json.dumps({"language": language})
        stream = await client.stt_stream(setup, audio_gen)
        step_index = 0
        # iter_text only surfaces transcripts; read the raw stream for VAD steps.
        async for msg in stream._stream:
            if msg.get("type") != "step":
                continue
            step_index += 1
            event = _gradium_vad_event(msg, step_index=step_index)
            if event is not None:
                events.append(event)


def _gradium_vad_event(msg: dict[str, Any], *, step_index: int) -> dict[str, Any] | None:
    vad = msg.get("vad")
    if not isinstance(vad, (list, tuple)) or len(vad) <= VAD_INACTIVITY_INDEX:
        return None
    entry = vad[VAD_INACTIVITY_INDEX]
    if not isinstance(entry, dict) or entry.get("inactivity_prob") is None:
        return None
    inactivity_prob = float(entry["inactivity_prob"])
    return {
        "event": "Step",
        "timestamp": round(step_index * VAD_STEP_S, 6),
        "p_eot": inactivity_prob,
        "inactivity_prob": inactivity_prob,
        "step_index": step_index,
    }


def _import_gradium_client():
    try:
        from gradium import client as gradium_client
    except ImportError as exc:
        raise RuntimeError("Gradium adapter requires the `gradium` package (`pip install gradium`).") from exc
    return gradium_client
