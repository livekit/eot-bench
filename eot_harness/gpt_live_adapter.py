"""Replay full turns through full-duplex GPT-Live on LiveKit Inference.

GPT-Live has no turn-detection events: it decides when to speak on its own. The
adapter streams a turn in real time, then records when the assistant's output
audio turns voiced. Its output stream is continuous and real-time paced, with
exact zeros for silence, so voiced frames give the onset on the input audio clock.

Each turn's events keep the raw evidence for rescoring:

- `OutputSpeech`: one voiced output segment (start, end, voiced seconds).
- `OutputTranscript`: one output transcript delta with its receive time.
- `OutputUtterance`: segments merged into one utterance and classified by
  what the model did, see `score_output_utterances`.
"""

from __future__ import annotations

import asyncio
import base64
import json
from contextlib import suppress
from typing import Any

import numpy as np

from .io import DEFAULT_INFERENCE_INTERVAL
from .languages import supports_any_benchmark_language
from .livekit_inference import inference_headers, inference_ws_url
from .streaming_stt import (
    DEFAULT_CHUNK_MS,
    build_event_prediction_rows,
    chunk_size_bytes,
    import_websockets,
    prepare_pcm16_audio,
)

GPT_LIVE_SAMPLE_RATE = 24000
DEFAULT_GPT_LIVE_MODEL = "openai/gpt-live-1"
DEFAULT_VOICE = "marin"
DEFAULT_INSTRUCTIONS = (
    "You are a helpful voice assistant on a phone call. Listen to the caller and reply "
    "when they have finished speaking. Keep replies brief."
)
DEFAULT_CONCURRENCY = 8
DEFAULT_POST_AUDIO_SILENCE_S = 5.0
DEFAULT_MERGE_GAP_S = 0.4
DEFAULT_VOICED_CAP_S = 2.0

OUTPUT_FRAME_SEC = 0.01
# Output silence is exact zeros; speech is an order of magnitude above this.
OUTPUT_SILENCE_RMS = 0.0006
# Finest gap kept between raw segments; scoring merges further.
RAW_SEGMENT_GAP_S = 0.1
# The output stream opens with a short tick; ignore voiced audio this early.
CONNECT_TICK_S = 0.5
SESSION_TIMEOUT_S = 20.0
_EPS = 1e-6


class GPTLiveAdapter:
    """Score when full-duplex GPT-Live starts speaking during a replayed turn."""

    display_name = "OpenAI GPT-Live"

    def __init__(
        self,
        *,
        model: str = DEFAULT_GPT_LIVE_MODEL,
        voice: str = DEFAULT_VOICE,
        instructions: str = DEFAULT_INSTRUCTIONS,
        chunk_ms: int = DEFAULT_CHUNK_MS,
        concurrency: int = DEFAULT_CONCURRENCY,
        post_audio_silence_s: float = DEFAULT_POST_AUDIO_SILENCE_S,
        merge_gap_s: float = DEFAULT_MERGE_GAP_S,
        voiced_cap_s: float = DEFAULT_VOICED_CAP_S,
    ) -> None:
        if not model:
            raise ValueError("model must be a non-empty string")
        if chunk_ms <= 0:
            raise ValueError("chunk_ms must be positive")
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        if post_audio_silence_s < 0:
            raise ValueError("post_audio_silence_s must be non-negative")
        if merge_gap_s < RAW_SEGMENT_GAP_S:
            raise ValueError(f"merge_gap_s must be at least {RAW_SEGMENT_GAP_S}")
        if voiced_cap_s <= 0:
            raise ValueError("voiced_cap_s must be positive")

        self.model = model
        self.voice = voice
        self.instructions = instructions
        self.chunk_ms = int(chunk_ms)
        self.concurrency = int(concurrency)
        self.post_audio_silence_s = float(post_audio_silence_s)
        self.merge_gap_s = float(merge_gap_s)
        self.voiced_cap_s = float(voiced_cap_s)

    @property
    def adapter_id(self) -> str:
        return f"livekit-inference/{self.model}"

    def supports_language(self, lang_code: str) -> bool:
        return supports_any_benchmark_language(lang_code)

    async def predict_turn(
        self,
        row: dict[str, Any],
        *,
        inference_interval: float = DEFAULT_INFERENCE_INTERVAL,
    ) -> dict[str, Any]:
        audio_bytes, audio_sec = prepare_pcm16_audio(row, sample_rate=GPT_LIVE_SAMPLE_RATE)
        speech, transcripts = await self._run_session(row["id"], audio_bytes)
        utterances = score_output_utterances(
            row,
            speech,
            merge_gap_s=self.merge_gap_s,
            voiced_cap_s=self.voiced_cap_s,
        )
        return {
            "id": row["id"],
            "audio_sec": audio_sec,
            "events": [*speech, *transcripts, *utterances],
            "prediction_rows": build_event_prediction_rows(
                row,
                utterances,
                inference_interval=inference_interval,
            ),
        }

    def _session_start(self) -> dict[str, Any]:
        return {
            "type": "session.start",
            "session": {
                "model": self.model,
                "instructions": self.instructions,
                "audio": {
                    "format": {"type": "audio/pcm", "rate": GPT_LIVE_SAMPLE_RATE},
                    "output": {"voice": self.voice},
                },
                "delegation": {"type": "client"},
            },
        }

    async def _run_session(self, row_id: Any, audio_bytes: bytes) -> tuple[list[dict], list[dict]]:
        websockets = import_websockets()
        loop = asyncio.get_running_loop()
        output = OutputSpeechTracker()
        transcripts: list[tuple[float, dict[str, Any]]] = []
        started = asyncio.Event()

        async def receive(ws) -> None:
            async for message in ws:
                data = json.loads(message)
                msg_type = data.get("type")
                if msg_type == "error":
                    raise RuntimeError(f"GPT-Live error for row {row_id!r}: {data}")
                if msg_type == "session.started":
                    started.set()
                elif msg_type == "session.output_audio.delta":
                    output.add(base64.b64decode(data.get("delta") or ""), received_at=loop.time())
                elif msg_type == "session.output_transcript.delta":
                    transcripts.append((loop.time(), data))
                elif msg_type == "session.closed":
                    return

        async with websockets.connect(
            inference_ws_url("live/sessions", model=self.model),
            additional_headers=inference_headers(),
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            recv_task = asyncio.create_task(receive(ws))
            try:
                await ws.send(json.dumps(self._session_start()))
                await _wait_for_start(started, recv_task)
                audio_start = loop.time()
                await self._stream_audio(ws, audio_bytes, recv_task)
                await ws.send(json.dumps({"type": "session.close"}))
                # session.closed confirms final usage; its absence does not invalidate the turn
                done, _ = await asyncio.wait({recv_task}, timeout=SESSION_TIMEOUT_S)
                if recv_task in done:
                    recv_task.result()
            finally:
                recv_task.cancel()
                with suppress(asyncio.CancelledError):
                    await recv_task

        speech = output.segments(audio_start=audio_start)
        transcript_events = [
            {
                "event": "OutputTranscript",
                "timestamp": round(received_at - audio_start, 3),
                "text": data.get("delta", ""),
                "start_ms": data.get("start_ms"),
                "end_ms": data.get("end_ms"),
            }
            for received_at, data in transcripts
        ]
        return speech, transcript_events

    async def _stream_audio(self, ws, audio_bytes: bytes, recv_task: asyncio.Task) -> None:
        """Send the turn, then trailing silence, paced against an absolute real-time schedule."""
        payload = audio_bytes + b"\x00\x00" * int(GPT_LIVE_SAMPLE_RATE * self.post_audio_silence_s)
        chunk_size = chunk_size_bytes(sample_rate=GPT_LIVE_SAMPLE_RATE, chunk_ms=self.chunk_ms)
        loop = asyncio.get_running_loop()
        start = loop.time()
        for index, offset in enumerate(range(0, len(payload), chunk_size)):
            delay = start + index * self.chunk_ms / 1000.0 - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            if recv_task.done():
                recv_task.result()
                raise RuntimeError("GPT-Live connection closed while streaming audio.")
            chunk = payload[offset : offset + chunk_size]
            await ws.send(
                json.dumps(
                    {
                        "type": "session.input_audio.append",
                        "audio": base64.b64encode(chunk).decode("ascii"),
                    },
                ),
            )


class OutputSpeechTracker:
    """Voiced 10 ms frames of a continuous PCM16 output stream, anchored to receive time."""

    def __init__(self, *, sample_rate: int = GPT_LIVE_SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate
        self.frame_samples = round(sample_rate * OUTPUT_FRAME_SEC)
        self.samples = 0
        self.voiced: list[bool] = []
        # Receive time of output sample 0: the earliest time consistent with every chunk,
        # since a real-time stream never delivers audio before it was produced.
        self.stream_start: float | None = None
        self._tail = np.zeros(0, dtype=np.float32)

    def add(self, pcm: bytes, *, received_at: float) -> None:
        if not pcm:
            return
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        self.samples += len(samples)
        start = received_at - self.samples / self.sample_rate
        self.stream_start = start if self.stream_start is None else min(self.stream_start, start)
        samples = np.concatenate([self._tail, samples])
        n_frames = len(samples) // self.frame_samples
        frames = samples[: n_frames * self.frame_samples].reshape(n_frames, self.frame_samples)
        self.voiced.extend((np.sqrt(np.mean(frames**2, axis=1)) > OUTPUT_SILENCE_RMS).tolist())
        self._tail = samples[n_frames * self.frame_samples :]

    def segments(self, *, audio_start: float) -> list[dict[str, Any]]:
        """`OutputSpeech` events on the input audio clock, which starts at `audio_start`."""
        if self.stream_start is None:
            return []
        offset = self.stream_start - audio_start
        return [
            {
                "event": "OutputSpeech",
                "timestamp": round(offset + start, 3),
                "end": round(offset + end, 3),
                "voiced_sec": round(voiced, 3),
            }
            for start, end, voiced in voiced_segments(self.voiced, frame_sec=OUTPUT_FRAME_SEC)
            if end > CONNECT_TICK_S
        ]


def voiced_segments(
    voiced: list[bool],
    *,
    frame_sec: float,
    max_gap_s: float = RAW_SEGMENT_GAP_S,
) -> list[tuple[float, float, float]]:
    """Group voiced frames into (start, end, voiced seconds), bridging gaps up to `max_gap_s`."""
    segments: list[list[float]] = []
    for index, is_voiced in enumerate(voiced):
        if not is_voiced:
            continue
        start = index * frame_sec
        if segments and start - segments[-1][1] <= max_gap_s + _EPS:
            segments[-1][1] = start + frame_sec
            segments[-1][2] += frame_sec
        else:
            segments.append([start, start + frame_sec, frame_sec])
    return [(start, end, voiced_sec) for start, end, voiced_sec in segments]


def score_output_utterances(
    row: dict[str, Any],
    speech: list[dict[str, Any]],
    *,
    merge_gap_s: float = DEFAULT_MERGE_GAP_S,
    voiced_cap_s: float = DEFAULT_VOICED_CAP_S,
) -> list[dict[str, Any]]:
    """Merge `OutputSpeech` segments into `OutputUtterance` events, classified by what the model did.

    - An utterance that starts in a silence span, or after the turn's audio, is a
      `floor` utterance at its onset.
    - An utterance that starts during user speech and is still going when the user
      pauses is a `floor` utterance at the start of that pause. `overlap_sec` is how
      long it overlapped the user.
    - An utterance that starts and ends during user speech is a `backchannel` if the
      model speaks again later, and an `interruption` if it never does: it was the
      model's reply, given before the user finished.

    Only `floor` utterances carry a `p_eot`: voiced length over `voiced_cap_s`,
    capped at 1, so the metric's threshold sweep separates short backchannels in a
    pause from replies.
    """
    spans = sorted(row["silence_spans"], key=lambda span: float(span["start"]))
    audio_end = max((float(span["end"]) for span in spans), default=0.0)
    utterances: list[dict[str, Any]] = []
    for segment in sorted(speech, key=lambda item: item["timestamp"]):
        if utterances and segment["timestamp"] - utterances[-1]["end"] <= merge_gap_s + _EPS:
            utterances[-1]["end"] = segment["end"]
            utterances[-1]["voiced_sec"] += segment["voiced_sec"]
        else:
            utterances.append(
                {
                    "onset": float(segment["timestamp"]),
                    "end": float(segment["end"]),
                    "voiced_sec": float(segment["voiced_sec"]),
                },
            )

    events = []
    for index, utterance in enumerate(utterances):
        onset, end = utterance["onset"], utterance["end"]
        in_span = any(float(s["start"]) - _EPS <= onset <= float(s["end"]) + _EPS for s in spans)
        reached = next((float(s["start"]) for s in spans if onset < float(s["start"]) < end - _EPS), None)
        if in_span or onset >= audio_end:
            kind, timestamp = "floor", onset
        elif reached is not None:
            kind, timestamp = "floor", reached
        else:
            kind = "backchannel" if index + 1 < len(utterances) else "interruption"
            timestamp = onset
        voiced_sec = round(utterance["voiced_sec"], 3)
        events.append(
            {
                "event": "OutputUtterance",
                "kind": kind,
                "timestamp": round(timestamp, 3),
                "p_eot": round(min(voiced_sec / voiced_cap_s, 1.0), 4) if kind == "floor" else None,
                "onset": round(onset, 3),
                "end": round(end, 3),
                "voiced_sec": voiced_sec,
                "overlap_sec": round(timestamp - onset, 3) if kind == "floor" else 0.0,
            },
        )
    return events


def turn_taking_summary(row: dict[str, Any], utterances: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-turn reply timing: the signed offset of the first reply from the user's end of turn.

    The offset is negative when the reply started before the user finished. The
    leaderboard latency clips it at the start of the pause; this keeps the overlap.
    """
    eot_start = float(max(row["silence_spans"], key=lambda span: float(span["start"]))["start"])
    reply = next(
        (u for u in utterances if u["kind"] == "floor" and u["timestamp"] >= eot_start - _EPS),
        None,
    )
    return {
        "id": row["id"],
        "interrupted": any(u["kind"] == "interruption" for u in utterances),
        "reply_offset_sec": None if reply is None else round(reply["onset"] - eot_start, 3),
    }


async def _wait_for_start(started: asyncio.Event, recv_task: asyncio.Task) -> None:
    """Wait for session.started, surfacing a receive-loop failure instead of timing out on it."""
    waiter = asyncio.ensure_future(started.wait())
    try:
        done, _ = await asyncio.wait(
            {waiter, recv_task},
            timeout=SESSION_TIMEOUT_S,
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        waiter.cancel()
    if started.is_set():
        return
    if recv_task in done:
        recv_task.result()
        raise RuntimeError("GPT-Live connection closed before session.started.")
    raise TimeoutError("Timed out waiting for GPT-Live session.started.")
