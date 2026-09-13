"""Streaming adapter for Baton, JoinIn AI's end-of-turn model.

Baton is a hosted service; this adapter is a thin client for it.

It scores each turn with a single stateless ``POST /v1/turn`` -- the whole turn in,
the full p_eot grid out. That is one request per turn rather than ~11k (one per grid
point), and because nothing is held open between calls the harness's ``--concurrency``
maps straight onto horizontally scaled instances.

The adapter passes ``row["messages"]`` as prior conversational context and sends only
the audio. It never reads ``row["words"]``, so the model is given nothing about the
turn it is being asked to judge beyond the audio up to that moment -- the same
constraint it operates under in production. There is a unit test asserting this.

Requires BATON_API_KEY. Request a beta key at hello@joinin.ai.
"""

from __future__ import annotations

import asyncio
import base64
import os
import random
from typing import Any

import numpy as np

from .io import DEFAULT_INFERENCE_INTERVAL, decode_audio
from .languages import supports_any_benchmark_language
from .streaming_stt import (
    SAMPLE_RATE,
    build_event_prediction_rows,
    resample_audio,
    resolve_api_key,
)

DEFAULT_BASE_URL = "https://baton.joinin.ai"
TURN_PATH = "/v1/turn"
DEFAULT_CONCURRENCY = 8

# 429 / 503: the server is busy or scaling, not broken. Always worth waiting for.
_CAPACITY_STATUS_CODES = (429, 503)
# Other server-side conditions where a fresh request may succeed.
_TRANSIENT_STATUS_CODES = (408, 500, 502, 504)


class BatonHTTPError(RuntimeError):
    """A non-200 response from Baton, tagged with its HTTP status."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"Baton returned HTTP {status}: {detail[:400]}")
        self.status = status


class BatonAdapter:
    """Scores a turn with one stateless POST to the Baton hosted API."""

    display_name = "Baton"
    score_point = 0.2

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "baton-v1",
        concurrency: int = DEFAULT_CONCURRENCY,
        # A cold instance can take minutes to become ready, so a request arriving
        # during a scale-up may wait. Retrying past that keeps a warm-up blip from
        # becoming a skipped turn under --skip-errors.
        max_retries: int = 4,
        retry_backoff: float = 5.0,
        # A 429 is "come back later", not a failure. It gets its own, more patient
        # budget. The two budgets are disjoint: an error is either capacity or
        # transient, never both.
        capacity_retries: int = 20,
        capacity_backoff_cap: float = 30.0,
        timeout: float = 300.0,
    ) -> None:
        if not model:
            raise ValueError("model must be a non-empty string")
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if retry_backoff < 0 or max_retries < 0 or capacity_retries < 0:
            raise ValueError("retry settings must be non-negative")
        self._api_key = api_key
        self._base_url = (base_url or os.environ.get("BATON_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model
        self.concurrency = int(concurrency)
        self.max_retries = int(max_retries)
        self.retry_backoff = float(retry_backoff)
        self.capacity_retries = int(capacity_retries)
        self.capacity_backoff_cap = float(capacity_backoff_cap)
        self.timeout = float(timeout)

    @property
    def adapter_id(self) -> str:
        return f"joinin/{self.model}"

    def supports_language(self, lang_code: str) -> bool:
        # English is materially stronger than the rest; it still scores every
        # benchmark language.
        return supports_any_benchmark_language(lang_code)

    async def predict_turn(
        self,
        row: dict[str, Any],
        *,
        inference_interval: float = DEFAULT_INFERENCE_INTERVAL,
    ) -> dict[str, Any]:
        api_key = self._api_key or resolve_api_key("BATON_API_KEY")
        pcm_bytes, audio_sec = _prepare_pcm16_audio(row, sample_rate=SAMPLE_RATE)
        # Prior turns only. Sending anything about the turn under judgement would
        # leak the future. Normalised client-side because the non-English splits
        # carry content: None, which a strict schema rejects with 422.
        messages = _clean_messages(row.get("messages"))

        attempt = capacity_attempt = 0
        while True:
            try:
                events = await self._score_events(
                    api_key=api_key,
                    pcm_bytes=pcm_bytes,
                    messages=messages,
                    inference_interval=inference_interval,
                )
                break
            except Exception as exc:
                if _is_capacity_error(exc):
                    if capacity_attempt >= self.capacity_retries:
                        raise
                    delay = min(self.capacity_backoff_cap, self.retry_backoff * (2**capacity_attempt))
                    capacity_attempt += 1
                elif _is_transient_error(exc):
                    if attempt >= self.max_retries:
                        raise
                    attempt += 1
                    delay = self.retry_backoff * attempt
                else:
                    raise
                # Full jitter so concurrent workers that were rejected together do
                # not retry in lockstep.
                await asyncio.sleep(random.uniform(0.0, delay))

        if not events:
            raise RuntimeError(f"No Baton events received for row {row['id']!r}.")

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
        *,
        api_key: str,
        pcm_bytes: bytes,
        messages: list[dict[str, str]],
        inference_interval: float,
    ) -> list[dict[str, Any]]:
        aiohttp = _import_aiohttp()
        url = f"{self._base_url}{TURN_PATH}"
        payload = {
            "audio_pcm16_b64": base64.b64encode(pcm_bytes).decode("ascii"),
            "messages": messages,
            "inference_interval": float(inference_interval),
            "sample_rate": SAMPLE_RATE,
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers={"X-API-Key": api_key}) as resp:
                if resp.status != 200:
                    raise BatonHTTPError(resp.status, await resp.text())
                try:
                    body = await resp.json()
                except Exception as exc:
                    raise RuntimeError(f"Baton returned a non-JSON 200 response: {exc}") from exc
        if not isinstance(body, dict) or not isinstance(body.get("events"), list):
            raise RuntimeError(f"Baton response has no 'events' list: {str(body)[:400]}")
        return [
            {"timestamp": float(e["timestamp"]), "p_eot": float(e["p_eot"])}
            for e in body["events"]
            if isinstance(e, dict) and e.get("timestamp") is not None and e.get("p_eot") is not None
        ]


def _import_aiohttp():
    try:
        import aiohttp
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("BatonAdapter requires aiohttp (uv run --with aiohttp ...)") from exc
    return aiohttp


def _prepare_pcm16_audio(row: dict[str, Any], *, sample_rate: int = SAMPLE_RATE) -> tuple[bytes, float]:
    """PCM16-encode a row's audio using Baton's scale convention.

    Baton's API contract specifies ``round(x * 32768)`` clipped into int16 range,
    while ``streaming_stt.pcm16le_bytes`` truncates ``x * 32767``. Decoding and
    resampling (including stereo down-mix) go through the shared helpers.
    """
    array, orig_sr = decode_audio(row["audio"])
    array = resample_audio(array, orig_sr, sample_rate)
    scaled = np.rint(np.clip(array, -1.0, 1.0) * 32768.0)
    pcm = np.clip(scaled, -32768.0, 32767.0).astype(np.int16)
    return pcm.tobytes(), float(len(array) / sample_rate)


def _clean_messages(messages) -> list[dict[str, str]]:
    """Coerce the dataset's message list into {role, content} strings."""
    out: list[dict[str, str]] = []
    for m in messages or []:
        out.append({"role": str(m.get("role") or "user"), "content": str(m.get("content") or "")})
    return out


def _is_capacity_error(exc: BaseException) -> bool:
    return isinstance(exc, BatonHTTPError) and exc.status in _CAPACITY_STATUS_CODES


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, BatonHTTPError):
        return exc.status in _TRANSIENT_STATUS_CODES
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError)):
        return True
    try:
        import aiohttp

        if isinstance(exc, aiohttp.ClientError):
            return True
    except ImportError:  # pragma: no cover
        pass
    return False
