"""Streaming adapter for the LiveKit Turn Detector v1.1 cloud end-of-turn model (`turn-detector-v1` in the SDK).

Speaks the agent-gateway EOT websocket protocol directly (reusing the protobuf
messages and auth helpers from ``livekit-agents``) rather than driving the live
``AudioTurnDetector`` FSM. For each scored silence-span grid point the adapter
streams audio up to that timestamp and issues an explicit inference request, so
every ``p(eot)`` reflects exactly the causal audio the harness exposes — and any
cloud error or timeout is a hard failure rather than a silent local fallback.

Run it through the streaming command, e.g.::

    eot-harness predict-streaming \\
      --path livekit/eot-bench-data --name all --split validation \\
      --adapter eot_harness.livekit_turn_detector_adapter:LiveKitTurnDetectorAdapter

Requires ``LIVEKIT_API_KEY`` and ``LIVEKIT_API_SECRET`` (env or constructor
arguments). The gateway URL defaults to ``LIVEKIT_INFERENCE_URL`` (falling back
to the production gateway); point it at a local server with e.g.
``LIVEKIT_INFERENCE_URL=http://localhost:8080/v1``.
"""

from __future__ import annotations

import asyncio
import math
import os
from typing import Any

from .io import DEFAULT_INFERENCE_INTERVAL, DEFAULT_MIN_SILENCE, _time_grid
from .languages import supports_any_benchmark_language, supports_language_code
from .streaming_stt import (
    SAMPLE_RATE,
    build_event_prediction_rows,
    chunk_size_bytes,
    prepare_pcm16_audio,
)

# Names the run (adapter_id and run directory) only: the gateway serves one EOT
# model and takes no model parameter.
DEFAULT_AUDIO_MODEL = "turn-detector-v1.1"
DEFAULT_CHUNK_MS = 100
DEFAULT_CONCURRENCY = 4
DEFAULT_PREDICT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 1.0
# Server / transport conditions worth retrying the whole turn for (the session
# is reconnected from scratch, so a retry is always safe).
_TRANSIENT_ERROR_CODES = (408, 429, 500, 502, 503, 504)
_EPS = 1e-6


class LiveKitTurnDetectorAdapter:
    """Stream turns through the LiveKit Turn Detector v1.1 cloud model and score p(eot)."""

    display_name = "LiveKit Turn Detector v1.1"
    score_point = 0.2

    def __init__(
        self,
        *,
        model: str = DEFAULT_AUDIO_MODEL,
        base_url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        chunk_ms: int = DEFAULT_CHUNK_MS,
        concurrency: int = DEFAULT_CONCURRENCY,
        predict_timeout: float = DEFAULT_PREDICT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    ) -> None:
        if not model:
            raise ValueError("model must be a non-empty string")
        if chunk_ms <= 0:
            raise ValueError("chunk_ms must be positive")
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        if predict_timeout <= 0:
            raise ValueError("predict_timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if retry_backoff < 0:
            raise ValueError("retry_backoff must be non-negative")

        self.model = model
        self.chunk_ms = int(chunk_ms)
        self.concurrency = int(concurrency)
        self.predict_timeout = float(predict_timeout)
        self.max_retries = int(max_retries)
        self.retry_backoff = float(retry_backoff)
        self._base_url = base_url
        self._api_key = api_key
        self._api_secret = api_secret
        self._supported_languages: set[str] | None = None
        self._languages_resolved = False

    @property
    def adapter_id(self) -> str:
        return f"livekit/{self.model}"

    def supports_language(self, lang_code: str) -> bool:
        languages = self._cloud_languages()
        if languages is None:
            # `livekit.agents.inference.eot` (CLOUD_LANGUAGES) is unreleased in some
            # builds; fall back to the benchmark's full language set.
            return supports_any_benchmark_language(lang_code)
        return supports_language_code(lang_code, languages)

    async def predict_turn(
        self,
        row: dict[str, Any],
        *,
        inference_interval: float = DEFAULT_INFERENCE_INTERVAL,
    ) -> dict[str, Any]:
        aiohttp = _import_aiohttp()
        proto = _import_proto()
        auth = _import_auth()

        api_key = self._api_key or os.environ.get("LIVEKIT_API_KEY")
        api_secret = self._api_secret or os.environ.get("LIVEKIT_API_SECRET")
        if not api_key or not api_secret:
            raise RuntimeError(
                "LiveKitTurnDetectorAdapter requires LIVEKIT_API_KEY and "
                "LIVEKIT_API_SECRET (env or constructor arguments).",
            )

        ws_url = self._base_url or auth.get_default_inference_url()
        if ws_url.startswith(("http://", "https://")):
            ws_url = ws_url.replace("http", "ws", 1)
        ws_url = f"{ws_url}/eot"
        headers = {
            **auth.get_inference_headers(),
            "Authorization": f"Bearer {auth.create_access_token(api_key, api_secret)}",
        }

        pcm_bytes, audio_sec = prepare_pcm16_audio(row, sample_rate=SAMPLE_RATE)
        total_samples = len(pcm_bytes) // 2
        query_timestamps = self._query_timestamps(row, inference_interval)
        chunk_size = chunk_size_bytes(sample_rate=SAMPLE_RATE, chunk_ms=self.chunk_ms)

        events: list[dict[str, Any]] = []
        for attempt in range(self.max_retries + 1):
            try:
                events = await self._score_events(
                    aiohttp,
                    proto,
                    ws_url,
                    headers,
                    pcm_bytes,
                    total_samples,
                    query_timestamps,
                    chunk_size,
                    row_id=row["id"],
                )
                break
            except Exception as exc:
                if attempt >= self.max_retries or not _is_transient_error(exc):
                    raise
                await asyncio.sleep(self.retry_backoff * (attempt + 1))

        return {
            "id": row["id"],
            "audio_sec": audio_sec,
            "events": events,
            "prediction_rows": build_event_prediction_rows(
                row,
                events,
                inference_interval=inference_interval,
            ),
        }

    async def _score_events(
        self,
        aiohttp,
        proto,
        ws_url: str,
        headers: dict[str, str],
        pcm_bytes: bytes,
        total_samples: int,
        query_timestamps: list[float],
        chunk_size: int,
        *,
        row_id: Any,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                ws_url, headers=headers, max_msg_size=0
            ) as ws:
                await self._send(
                    ws,
                    proto.ClientMessage(
                        session_create=proto.SessionCreate(
                            settings=proto.SessionSettings(
                                sample_rate=SAMPLE_RATE,
                                encoding=proto.AUDIO_ENCODING_PCM_S16LE,
                            ),
                        ),
                    ),
                )

                sent_samples = 0
                for index, timestamp in enumerate(query_timestamps):
                    target = min(
                        total_samples, int(math.floor(timestamp * SAMPLE_RATE + _EPS))
                    )
                    if target > sent_samples:
                        await self._send_audio(
                            ws, proto, pcm_bytes, sent_samples, target, chunk_size
                        )
                        sent_samples = target

                    request_id = f"{row_id}-{index}"
                    await self._send(
                        ws,
                        proto.ClientMessage(
                            inference_start=proto.InferenceStart(request_id=request_id)
                        ),
                    )
                    prob = await asyncio.wait_for(
                        self._await_prediction(ws, proto, request_id, row_id=row_id),
                        timeout=self.predict_timeout,
                    )
                    events.append({"timestamp": float(timestamp), "p_eot": float(prob)})

                await self._send(
                    ws, proto.ClientMessage(session_close=proto.SessionClose())
                )
        return events

    def _query_timestamps(
        self, row: dict[str, Any], inference_interval: float
    ) -> list[float]:
        """Grid points the harness will score, matching ``build_event_prediction_rows``."""
        timestamps: set[float] = set()
        for span in row["silence_spans"]:
            start = float(span["start"])
            end = float(span["end"])
            if end - start < DEFAULT_MIN_SILENCE - _EPS:
                continue
            timestamps.update(_time_grid(start, end, inference_interval))
        return sorted(timestamps)

    def _cloud_languages(self) -> set[str] | None:
        if not self._languages_resolved:
            self._languages_resolved = True
            try:
                from livekit.agents.inference.eot.languages import CLOUD_LANGUAGES

                self._supported_languages = set(CLOUD_LANGUAGES.keys())
            except ImportError:
                self._supported_languages = None
        return self._supported_languages

    async def _send_audio(
        self,
        ws,
        proto,
        pcm_bytes: bytes,
        start_sample: int,
        end_sample: int,
        chunk_size: int,
    ) -> None:
        start_byte = start_sample * 2
        end_byte = end_sample * 2
        for offset in range(start_byte, end_byte, chunk_size):
            segment = pcm_bytes[offset : min(offset + chunk_size, end_byte)]
            if not segment:
                continue
            await self._send(
                ws,
                proto.ClientMessage(
                    input_audio=proto.InputAudio(
                        audio=segment,
                        num_samples=len(segment) // 2,
                        created_at=_now(),
                    ),
                ),
            )

    async def _await_prediction(
        self, ws, proto, request_id: str, *, row_id: Any
    ) -> float:
        import aiohttp

        while True:
            msg = await ws.receive()
            if msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSING,
                aiohttp.WSMsgType.ERROR,
            ):
                raise _EotServerError(
                    f"eot websocket closed unexpectedly for row {row_id!r}: {msg.type}",
                    transient=True,
                )
            if msg.type != aiohttp.WSMsgType.BINARY:
                continue

            server_msg = proto.ServerMessage()
            server_msg.ParseFromString(msg.data)
            which = server_msg.WhichOneof("message")
            if which == "error":
                code = server_msg.error.code
                raise _EotServerError(
                    f"eot server error for row {row_id!r}: "
                    f"{server_msg.error.message} (code={code})",
                    code=code,
                    transient=code in _TRANSIENT_ERROR_CODES,
                )
            if which == "eot_prediction" and server_msg.request_id == request_id:
                return server_msg.eot_prediction.probability
            # Ignore session_created / inference_started / inference_stopped / etc.

    @staticmethod
    async def _send(ws, msg) -> None:
        await ws.send_bytes(msg.SerializeToString())


class _EotServerError(RuntimeError):
    """An EOT websocket error, tagged with whether retrying the turn may help."""

    def __init__(
        self, message: str, *, code: int | None = None, transient: bool = False
    ) -> None:
        super().__init__(message)
        self.code = code
        self.transient = transient


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, _EotServerError):
        return exc.transient
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError)):
        return True
    try:
        import aiohttp

        if isinstance(exc, aiohttp.ClientError):
            return True
    except ImportError:
        pass
    return False


def _now():
    from google.protobuf.timestamp_pb2 import Timestamp

    ts = Timestamp()
    ts.GetCurrentTime()
    return ts


def _import_aiohttp():
    try:
        import aiohttp
    except ImportError as exc:
        raise RuntimeError(
            "LiveKit audio adapter requires the `aiohttp` package."
        ) from exc
    return aiohttp


def _import_auth():
    try:
        from livekit.agents.inference import _utils
    except ImportError as exc:
        raise RuntimeError(
            "LiveKit audio adapter requires `livekit-agents` for cloud auth helpers.",
        ) from exc
    return _utils


def _import_proto():
    try:
        from livekit.protocol.agent_pb import agent_inference
    except ImportError as exc:
        raise RuntimeError(
            "LiveKit audio adapter requires `livekit-agents` (livekit.protocol) "
            "for the EOT websocket protocol.",
        ) from exc
    return agent_inference
