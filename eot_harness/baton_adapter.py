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
from typing import Any

import numpy as np

from .languages import supports_any_benchmark_language
from .io import decode_audio
from .streaming_stt import (
    build_event_prediction_rows,
    resample_audio,
    resolve_api_key,
)

DEFAULT_BASE_URL = "https://baton.joinin.ai"
TURN_PATH = "/v1/turn"
DEFAULT_INFERENCE_INTERVAL = 0.1
SAMPLE_RATE = 16000


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
        # A cold instance can take minutes to become ready, so a request arriving
        # during a scale-up may wait. Retrying past that is the difference between a
        # warm-up blip and a silently dropped turn -- the harness is often invoked
        # with --skip-errors, which would quietly shrink the eval set rather than
        # fail loudly.
        max_retries: int = 4,
        retry_backoff: float = 5.0,
        # A 429 is not a failure, it is "come back later" -- capacity, not breakage.
        # It WILL succeed given time, so it gets its own far more patient budget:
        # a dropped turn silently shrinks the eval set, which is worse than a slow run.
        capacity_retries: int = 20,
        capacity_backoff_cap: float = 30.0,
        timeout: float = 300.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = (base_url or os.environ.get("BATON_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model
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

        events: list[dict[str, Any]] = []
        attempt = capacity_attempt = 0
        while True:
            try:
                events = await self._score_events(
                    api_key=api_key,
                    pcm_bytes=pcm_bytes,
                    # Prior turns only. Sending anything about the turn under
                    # judgement would leak the future and flatter every number.
                    # Normalised here as well as server-side: the benchmark's
                    # non-English splits carry content: None, which a strict schema
                    # rejects with 422. Doing it client-side means the run works
                    # against a server that has not been updated yet.
                    messages=_clean_messages(row.get("messages")),
                    inference_interval=inference_interval,
                )
                break
            except Exception as exc:
                # Capacity gets its own budget. Every turn must be scored: a turn
                # dropped here vanishes from the metrics with nothing in the output
                # saying so, and would read as the model failing rather than the
                # server being busy.
                if _is_capacity_error(exc) and capacity_attempt < self.capacity_retries:
                    delay = min(self.capacity_backoff_cap,
                                self.retry_backoff * (2 ** capacity_attempt))
                    capacity_attempt += 1
                    await asyncio.sleep(delay)
                    continue
                if _is_transient_error(exc) and attempt < self.max_retries:
                    attempt += 1
                    await asyncio.sleep(self.retry_backoff * attempt)
                    continue
                raise

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
                    detail = await resp.text()
                    raise RuntimeError(f"Baton returned HTTP {resp.status}: {detail[:400]}")
                body = await resp.json()
        return [
            {"timestamp": float(e["timestamp"]), "p_eot": float(e["p_eot"])}
            for e in body.get("events", [])
            if e.get("timestamp") is not None and e.get("p_eot") is not None
        ]


def _import_aiohttp():
    try:
        import aiohttp
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("BatonAdapter requires aiohttp (uv run --with aiohttp ...)") from exc
    return aiohttp


def _prepare_pcm16_audio(row: dict[str, Any], *, sample_rate: int = SAMPLE_RATE) -> tuple[bytes, float]:
    """PCM16-encode a row's audio using Baton's scale convention.

    Deliberately not ``streaming_stt.prepare_pcm16_audio``: that helper scales
    by 32767, which shifts every sample by one LSB. That is tolerable for some
    consumers, but it is a measurable quality cost for anything sensitive to exact
    sample values. Encoding as round(x * 32768) clipped into int16 range is what
    Baton's API contract specifies.
    """
    audio = row.get("audio") or {}
    if "array" in audio:
        # already-decoded shape (the batch path, and hand-built test rows)
        array = np.asarray(audio["array"], dtype=np.float32)
        orig_sr = int(audio["sampling_rate"])
    else:
        # A STREAMING adapter is handed the raw row, and the harness loads the
        # dataset with Audio(decode=False) -- so `audio` is {bytes, path} and must
        # be decoded here. Assuming the decoded shape passes every unit test built
        # on synthetic rows and then KeyErrors on the first real turn.
        array, orig_sr = decode_audio(audio)
        array = np.asarray(array, dtype=np.float32)
        orig_sr = int(orig_sr)
    if orig_sr != sample_rate:
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
    """429 / 503: the server is busy or scaling, not broken. Always worth waiting for."""
    m = str(exc)
    return "429" in m or "503" in m


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError)):
        return True
    message = str(exc).lower()
    return any(token in message for token in ("timeout", "temporarily", "502", "503", "504", "429", "reset"))
