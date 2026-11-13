from __future__ import annotations

import asyncio
import inspect
import types

from eot_harness import livekit_turn_detector_adapter as module
from eot_harness.livekit_turn_detector_adapter import (
    DEFAULT_AUDIO_MODEL,
    LiveKitTurnDetectorAdapter,
)


def test_livekit_turn_detector_adapter_defaults() -> None:
    params = inspect.signature(LiveKitTurnDetectorAdapter.__init__).parameters

    assert LiveKitTurnDetectorAdapter.score_point == 0.2
    assert LiveKitTurnDetectorAdapter.display_name == "LiveKit Turn Detector v1.1"
    assert params["model"].default == DEFAULT_AUDIO_MODEL
    assert params["chunk_ms"].default == 100
    assert params["base_url"].default is None


def test_livekit_turn_detector_adapter_is_streaming() -> None:
    adapter = LiveKitTurnDetectorAdapter()

    assert adapter.adapter_id == "livekit/turn-detector-v1.1"
    assert callable(adapter.predict_turn)
    assert inspect.iscoroutinefunction(adapter.predict_turn)


def test_livekit_turn_detector_adapter_query_timestamps_match_scored_grid() -> None:
    adapter = LiveKitTurnDetectorAdapter()
    row = {
        "id": "turn-1",
        "silence_spans": [
            {"start": 0.5, "end": 0.55},  # shorter than min silence; skipped
            {"start": 1.0, "end": 1.3},
        ],
    }

    timestamps = adapter._query_timestamps(row, 0.1)

    assert timestamps == [1.0, 1.1, 1.2, 1.3]


class _FakeWebSocket:
    def __init__(self, proto) -> None:
        self.proto = proto
        self.sent: list = []
        self._pending: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def send_bytes(self, data: bytes) -> None:
        msg = self.proto.ClientMessage()
        msg.ParseFromString(data)
        self.sent.append(msg)
        if msg.WhichOneof("message") == "inference_start":
            self._pending.append(msg.inference_start.request_id)

    async def receive(self):
        import aiohttp

        reply = self.proto.ServerMessage(
            request_id=self._pending.pop(0),
            eot_prediction=self.proto.EotPrediction(probability=0.5),
        )
        return types.SimpleNamespace(type=aiohttp.WSMsgType.BINARY, data=reply.SerializeToString())


class _FakeSession:
    def __init__(self, ws: _FakeWebSocket) -> None:
        self.ws = ws

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    def ws_connect(self, *args, **kwargs) -> _FakeWebSocket:
        return self.ws


def _score(agent_text: str):
    proto = module._import_proto()
    ws = _FakeWebSocket(proto)
    fake_aiohttp = types.SimpleNamespace(ClientSession=lambda: _FakeSession(ws))
    adapter = LiveKitTurnDetectorAdapter()
    events = asyncio.run(
        adapter._score_events(
            fake_aiohttp,
            proto,
            "ws://test/eot",
            {},
            b"\x00\x00" * 16000,
            16000,
            [0.5, 1.0],
            3200,
            agent_text=agent_text,
            row_id="turn-1",
        )
    )
    return events, ws.sent


def test_livekit_turn_detector_adapter_sends_agent_context_and_turn_samples() -> None:
    events, sent = _score("How can I help?")

    assert [e["timestamp"] for e in events] == [0.5, 1.0]
    kinds = [m.WhichOneof("message") for m in sent]
    starts = [i for i, kind in enumerate(kinds) if kind == "inference_start"]
    assert [sent[i].inference_start.turn_samples for i in starts] == [8000, 16000]
    for i in starts:
        context = sent[i - 1].eot_input_chat_context
        assert kinds[i - 1] == "eot_input_chat_context"
        assert [c.text for m in context.messages for c in m.content] == ["How can I help?"]


def test_livekit_turn_detector_adapter_sends_empty_context_without_agent_text() -> None:
    _, sent = _score("")

    contexts = [m for m in sent if m.WhichOneof("message") == "eot_input_chat_context"]
    assert len(contexts) == 2
    assert all(len(m.eot_input_chat_context.messages) == 0 for m in contexts)


def test_last_assistant_text_reads_the_last_assistant_message() -> None:
    messages = [
        {"role": "assistant", "content": "Hi there."},
        {"role": "user", "content": "Hello."},
        {"role": "assistant", "content": "  What is your name?  "},
        {"role": "user", "content": "It is"},
    ]

    assert module._last_assistant_text(messages) == "What is your name?"
    assert module._last_assistant_text([{"role": "user", "content": "x"}]) == ""
    assert module._last_assistant_text(None) == ""


def test_livekit_turn_detector_adapter_waits_out_rate_limits(monkeypatch) -> None:
    import numpy as np

    adapter = LiveKitTurnDetectorAdapter(
        api_key="key", api_secret="secret", max_retries=0, retry_backoff=0.0, capacity_retries=2
    )
    calls = []

    async def score_events(*args, **kwargs):
        calls.append(1)
        if len(calls) <= 2:
            raise module._EotServerError("quota exceeded", code=429, transient=True)
        return [{"timestamp": 1.0, "p_eot": 0.9}]

    monkeypatch.setattr(adapter, "_score_events", score_events)
    row = {
        "id": "turn-1",
        "language": "en",
        "audio": {"array": np.zeros(32000, dtype=np.float32), "sampling_rate": 16000},
        "silence_spans": [{"start": 1.0, "end": 1.3}],
    }

    result = asyncio.run(adapter.predict_turn(row))

    assert len(calls) == 3
    assert result["prediction_rows"][0]["p_eot"] == 0.9

    # A third 429 exceeds the capacity budget and falls back to `max_retries`.
    calls.clear()
    adapter.capacity_retries = 1
    try:
        asyncio.run(adapter.predict_turn(row))
    except module._EotServerError as exc:
        assert exc.code == 429
    else:
        raise AssertionError("expected the 429 to surface")
