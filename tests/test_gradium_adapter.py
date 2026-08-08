from __future__ import annotations

import asyncio
import json

import pytest

from eot_harness.gradium_adapter import GradiumStreamingAdapter, _gradium_vad_event
from eot_harness.streaming_stt import build_event_prediction_rows, resolve_api_key


def _step_msg(inactivity_prob: float) -> dict:
    return {
        "type": "step",
        "vad": [
            {"inactivity_prob": 0.01},
            {"inactivity_prob": 0.02},
            {"inactivity_prob": 0.03},
            {"inactivity_prob": inactivity_prob},
        ],
    }


def test_gradium_vad_event_uses_fourth_vad_entry():
    event = _gradium_vad_event(_step_msg(0.83), step_index=5)

    assert event == {
        "event": "Step",
        "timestamp": 0.4,
        "p_eot": 0.83,
        "inactivity_prob": 0.83,
        "step_index": 5,
    }


def test_gradium_vad_event_returns_none_on_malformed_payloads():
    assert _gradium_vad_event({"type": "step"}, step_index=1) is None
    assert _gradium_vad_event({"type": "step", "vad": []}, step_index=1) is None
    assert _gradium_vad_event({"type": "step", "vad": [{}, {}, {}]}, step_index=1) is None
    assert _gradium_vad_event({"type": "step", "vad": [{}, {}, {}, {}]}, step_index=1) is None


def test_gradium_defaults_and_key(monkeypatch):
    monkeypatch.setenv("GRADIUM_API_KEY", "gradium-test-key")
    adapter = GradiumStreamingAdapter()

    assert adapter.adapter_id == "gradium/default"
    assert adapter.display_name == "Gradium"
    assert not hasattr(adapter, "score_point")
    assert adapter.url == "https://api.gradium.ai/api"
    assert adapter.chunk_ms == 80
    assert adapter.eot_threshold == 0.5
    assert adapter.supports_language("en")
    assert adapter.supports_language("ja")
    assert not adapter.supports_language("xx")
    assert resolve_api_key("GRADIUM_API_KEY") == "gradium-test-key"


def test_gradium_url_override():
    assert GradiumStreamingAdapter(url="http://localhost:8080/api").url == "http://localhost:8080/api"


def test_gradium_constructor_validation():
    with pytest.raises(ValueError, match="model"):
        GradiumStreamingAdapter(model="")
    with pytest.raises(ValueError, match="chunk_ms"):
        GradiumStreamingAdapter(chunk_ms=0)
    with pytest.raises(ValueError, match="concurrency"):
        GradiumStreamingAdapter(concurrency=0)
    with pytest.raises(ValueError, match="eot_threshold"):
        GradiumStreamingAdapter(eot_threshold=1.5)


class _FakeSTTStream:
    def __init__(self, messages):
        async def gen():
            for message in messages:
                yield message

        self._stream = gen()


class _FakeGradiumClient:
    def __init__(self, messages):
        self.messages = messages
        self.setup = None

    async def stt_stream(self, setup, audio_gen):
        self.setup = setup
        async for _ in audio_gen:
            pass
        return _FakeSTTStream(self.messages)


def test_gradium_collect_events_maps_steps_to_80ms_grid():
    adapter = GradiumStreamingAdapter()
    client = _FakeGradiumClient(
        [
            {"type": "ready"},
            _step_msg(0.1),
            {"type": "text", "text": "hello"},
            _step_msg(0.2),
            {"type": "step", "vad": None},
            _step_msg(0.9),
        ],
    )

    async def audio_gen():
        yield b"\x00\x00"

    events: list[dict] = []
    asyncio.run(adapter._collect_events(client, audio_gen(), events))

    assert client.setup == {"model_name": "default", "input_format": "pcm"}
    assert [event["timestamp"] for event in events] == [0.08, 0.16, 0.32]
    assert [event["p_eot"] for event in events] == [0.1, 0.2, 0.9]
    assert [event["step_index"] for event in events] == [1, 2, 4]


@pytest.mark.parametrize("language", ["en", "fr", "pt", "es", "de"])
def test_gradium_collect_events_sets_language_json_config(language):
    adapter = GradiumStreamingAdapter()
    client = _FakeGradiumClient([_step_msg(0.1)])

    async def audio_gen():
        yield b"\x00\x00"

    events: list[dict] = []
    asyncio.run(adapter._collect_events(client, audio_gen(), events, language=language))

    assert json.loads(client.setup["json_config"]) == {"language": language}


@pytest.mark.parametrize("language", [None, "ja", "it"])
def test_gradium_collect_events_omits_unsupported_language(language):
    adapter = GradiumStreamingAdapter()
    client = _FakeGradiumClient([_step_msg(0.1)])

    async def audio_gen():
        yield b"\x00\x00"

    events: list[dict] = []
    asyncio.run(adapter._collect_events(client, audio_gen(), events, language=language))

    assert "json_config" not in client.setup


def test_gradium_events_feed_prediction_rows():
    row = {
        "id": "turn-1",
        "silence_spans": [
            {"start": 0.1, "end": 0.5},
            {"start": 1.0, "end": 1.3},
        ],
    }
    events = [
        _gradium_vad_event(_step_msg(prob), step_index=index + 1)
        for index, prob in enumerate([0.05, 0.1, 0.2, 0.3, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.2, 0.4, 0.6, 0.8, 0.9])
    ]

    rows = build_event_prediction_rows(row, events, inference_interval=0.1)

    assert {r["label"] for r in rows if r["span_index"] == 0} == {"hold"}
    assert {r["label"] for r in rows if r["span_index"] == 1} == {"eot"}
    assert max(r["p_eot"] for r in rows if r["span_index"] == 1) == 0.9
