from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.parse import urlencode

from .io import DEFAULT_INFERENCE_INTERVAL
from .languages import supports_language_code
from .streaming_stt import (
    DEFAULT_CHUNK_MS,
    SAMPLE_RATE,
    build_event_prediction_rows,
    chunk_size_bytes,
    import_websockets,
    prepare_pcm16_audio,
    resolve_api_key,
)

DEFAULT_CARTESIA_MODEL = "ink-2"
DEFAULT_CONCURRENCY = 4
CARTESIA_API_VERSION = "2026-03-01"
CARTESIA_SUPPORTED_LANGUAGES = {"en"}


class CartesiaStreamingAdapter:
    """Replay full turns through Cartesia Ink and score native turn-end events."""

    display_name = "Cartesia Ink 2"

    def __init__(
        self,
        *,
        model: str = DEFAULT_CARTESIA_MODEL,
        chunk_ms: int = DEFAULT_CHUNK_MS,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        if not model:
            raise ValueError("model must be a non-empty string")
        if chunk_ms <= 0:
            raise ValueError("chunk_ms must be positive")
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")

        self.model = model
        self.chunk_ms = int(chunk_ms)
        self.concurrency = int(concurrency)

    @property
    def adapter_id(self) -> str:
        return f"cartesia/{self.model}"

    def supports_language(self, lang_code: str) -> bool:
        return supports_language_code(lang_code, CARTESIA_SUPPORTED_LANGUAGES)

    async def predict_turn(
        self,
        row: dict[str, Any],
        *,
        inference_interval: float = DEFAULT_INFERENCE_INTERVAL,
    ) -> dict[str, Any]:
        return await self._replay_turn(
            row,
            resolve_api_key("CARTESIA_API_KEY"),
            inference_interval=inference_interval,
        )

    async def _replay_turn(
        self,
        row: dict[str, Any],
        api_key: str,
        *,
        inference_interval: float,
    ) -> dict[str, Any]:
        websockets = import_websockets()
        audio_bytes, total_audio_sec = prepare_pcm16_audio(row, sample_rate=SAMPLE_RATE)
        chunk_size = chunk_size_bytes(sample_rate=SAMPLE_RATE, chunk_ms=self.chunk_ms)
        url = f"wss://api.cartesia.ai/stt/turns/websocket?{urlencode(self._connection_params())}"
        events: list[dict[str, Any]] = []

        async with websockets.connect(
            url,
            additional_headers={
                "Authorization": f"Bearer {api_key}",
                "Cartesia-Version": CARTESIA_API_VERSION,
            },
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            started = time.perf_counter()
            recv_task = asyncio.create_task(
                _recv_cartesia_events(ws, row_id=row["id"], events=events, started=started),
            )
            for start in range(0, len(audio_bytes), chunk_size):
                await ws.send(audio_bytes[start : start + chunk_size])
                await asyncio.sleep(self.chunk_ms / 1000.0)
            await ws.send(json.dumps({"type": "close"}))
            try:
                await asyncio.wait_for(recv_task, timeout=15.0)
            except asyncio.TimeoutError as exc:
                recv_task.cancel()
                raise RuntimeError(f"Timed out waiting for Cartesia close on {row['id']!r}.") from exc

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

    def _connection_params(self) -> dict[str, str]:
        return {
            "model": self.model,
            "encoding": "pcm_s16le",
            "sample_rate": str(SAMPLE_RATE),
        }


async def _recv_cartesia_events(
    ws,
    *,
    row_id: Any,
    events: list[dict[str, Any]],
    started: float,
) -> None:
    async for message in ws:
        data = json.loads(message)
        if data.get("type") == "error":
            raise RuntimeError(f"Cartesia error for row {row_id!r}: {data}")
        event = _cartesia_endpoint_event(
            data,
            received_audio_sec=time.perf_counter() - started,
        )
        if event is not None:
            events.append(event)


def _cartesia_endpoint_event(
    data: dict[str, Any],
    *,
    received_audio_sec: float,
) -> dict[str, Any] | None:
    if data.get("type") != "turn.end":
        return None

    return {
        "event": "TurnEnd",
        "timestamp": float(received_audio_sec),
        "p_eot": 1.0,
        "transcript": data.get("transcript", ""),
        "request_id": data.get("request_id"),
    }
