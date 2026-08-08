from __future__ import annotations

import pytest

from eot_harness.assemblyai_adapter import AssemblyAIStreamingAdapter, _assemblyai_event_from_turn
from eot_harness.cartesia_adapter import CartesiaStreamingAdapter, _cartesia_endpoint_event
from eot_harness.openai_realtime_adapter import OpenAIRealtime2Adapter, _openai_speech_stopped_event
from eot_harness.soniox_adapter import SonioxStreamingAdapter, _soniox_endpoint_event
from eot_harness.streaming_stt import build_event_prediction_rows, resolve_api_key
from eot_harness.xai_stt_adapter import XAIStreamingSTTAdapter, _xai_endpoint_event


def _row():
    return {
        "id": "turn-1",
        "silence_spans": [
            {"start": 1.0, "end": 1.4},
            {"start": 2.0, "end": 2.3},
        ],
    }


def test_build_event_prediction_rows_forwards_latest_score():
    rows = build_event_prediction_rows(
        _row(),
        [
            {"event": "ignored", "timestamp": None, "p_eot": None},
            {"event": "before_span", "timestamp": 0.9, "p_eot": 1.0},
            {"event": "low", "timestamp": 1.2, "p_eot": 0.12},
            {"event": "endpoint", "timestamp": 2.2, "p_eot": 1.0},
        ],
        inference_interval=0.2,
    )

    assert [row["timestamp"] for row in rows] == [1.0, 1.2, 1.4, 2.0, 2.2, 2.3]
    assert [row["label"] for row in rows] == ["hold", "hold", "hold", "eot", "eot", "eot"]
    assert [row["p_eot"] for row in rows] == [0.0, 0.12, 0.12, 0.0, 1.0, 1.0]


def test_build_event_prediction_rows_all_zero_when_no_events():
    rows = build_event_prediction_rows(
        _row(),
        [],
        inference_interval=0.2,
    )

    assert [row["timestamp"] for row in rows] == [1.0, 1.2, 1.4, 2.0, 2.2, 2.3]
    assert [row["p_eot"] for row in rows] == [0.0] * 6


def test_assemblyai_turn_event_uses_realtime_receive_position():
    event = _assemblyai_event_from_turn(
        {
            "type": "Turn",
            "turn_order": 2,
            "end_of_turn": True,
            "end_of_turn_confidence": 0.72,
            "transcript": "done",
            "utterance": "done",
        },
        received_audio_sec=1.35,
    )

    assert event == {
        "event": "Turn",
        "timestamp": 1.35,
        "p_eot": 0.72,
        "end_of_turn": True,
        "end_of_turn_confidence": 0.72,
        "turn_order": 2,
        "transcript": "done",
        "utterance": "done",
    }


def test_assemblyai_defaults_and_key(monkeypatch):
    monkeypatch.delenv("ASSEMBLYAI_API_KEY", raising=False)
    monkeypatch.setenv("ASSEMBLY_API_KEY", "aai-test-key")
    adapter = AssemblyAIStreamingAdapter()

    assert adapter.adapter_id == "assemblyai/universal-streaming-multilingual"
    assert adapter.display_name == "AssemblyAI"
    assert not hasattr(adapter, "score_point")
    assert adapter.supports_language("en")
    assert adapter.supports_language("fr")
    assert adapter.supports_language("de")
    assert adapter.supports_language("es")
    assert adapter.supports_language("it")
    assert adapter.supports_language("pt")
    assert not adapter.supports_language("ja")
    assert resolve_api_key("ASSEMBLYAI_API_KEY", "ASSEMBLY_API_KEY", "ASSEMBLY_AI_KEY") == "aai-test-key"
    assert adapter._connection_params() == {
        "speech_model": "universal-streaming-multilingual",
        "encoding": "pcm_s16le",
        "sample_rate": "16000",
        "min_turn_silence": "100",
        "max_turn_silence": "3000",
        "end_of_turn_confidence_threshold": "0.1",
    }


def test_assemblyai_english_model_supports_only_english():
    adapter = AssemblyAIStreamingAdapter(model="universal-streaming-english")

    assert adapter.supports_language("en")
    assert not adapter.supports_language("es")
    assert not adapter.supports_language("fr")


def test_assemblyai_unknown_model_supports_no_benchmark_languages():
    adapter = AssemblyAIStreamingAdapter(model="unknown-model")

    assert not adapter.supports_language("en")
    assert not adapter.supports_language("es")


def test_assemblyai_turn_silence_validation():
    with pytest.raises(ValueError, match="min_turn_silence"):
        AssemblyAIStreamingAdapter(min_turn_silence=-1)
    with pytest.raises(ValueError, match="max_turn_silence"):
        AssemblyAIStreamingAdapter(max_turn_silence=-1)
    with pytest.raises(ValueError, match="max_turn_silence must be >= min_turn_silence"):
        AssemblyAIStreamingAdapter(min_turn_silence=500, max_turn_silence=100)


def test_cartesia_turn_end_event_uses_realtime_receive_position():
    event = _cartesia_endpoint_event(
        {
            "type": "turn.end",
            "transcript": "done",
            "request_id": "request-1",
        },
        received_audio_sec=1.35,
    )

    assert event == {
        "event": "TurnEnd",
        "timestamp": 1.35,
        "p_eot": 1.0,
        "transcript": "done",
        "request_id": "request-1",
    }


def test_cartesia_ignores_eager_end_until_turn_is_definitive():
    event = _cartesia_endpoint_event(
        {"type": "turn.eager_end", "transcript": "maybe done"},
        received_audio_sec=1.1,
    )

    assert event is None


def test_cartesia_defaults_and_key(monkeypatch):
    monkeypatch.setenv("CARTESIA_API_KEY", "cartesia-test-key")
    adapter = CartesiaStreamingAdapter()

    assert adapter.adapter_id == "cartesia/ink-2"
    assert adapter.display_name == "Cartesia Ink 2"
    assert not hasattr(adapter, "score_point")
    assert adapter.supports_language("en")
    assert not adapter.supports_language("es")
    assert resolve_api_key("CARTESIA_API_KEY") == "cartesia-test-key"
    assert adapter._connection_params() == {
        "model": "ink-2",
        "encoding": "pcm_s16le",
        "sample_rate": "16000",
    }


def test_soniox_endpoint_event_detects_final_end_token():
    event = _soniox_endpoint_event(
        {
            "tokens": [
                {"text": "hello", "is_final": True, "end_ms": 600},
                {"text": "<end>", "is_final": True},
            ],
            "final_audio_proc_ms": 1250,
            "total_audio_proc_ms": 1300,
        },
    )

    assert event == {
        "event": "Endpoint",
        "timestamp": 1.25,
        "p_eot": 1.0,
        "token": "<end>",
        "final_audio_proc_ms": 1250,
        "total_audio_proc_ms": 1300,
    }


def test_soniox_defaults_and_key(monkeypatch):
    monkeypatch.setenv("SONIOX_API_KEY", "soniox-test-key")
    adapter = SonioxStreamingAdapter()

    assert adapter.adapter_id == "soniox/stt-rt-preview"
    assert adapter.display_name == "Soniox"
    assert not hasattr(adapter, "score_point")
    assert adapter.supports_language("ja")
    assert resolve_api_key("SONIOX_API_KEY") == "soniox-test-key"
    start = adapter._start_message("redacted", language="de")
    assert start["enable_endpoint_detection"] is True
    assert start["language_hints"] == ["de"]


def test_xai_endpoint_event_uses_start_plus_duration():
    event = _xai_endpoint_event(
        {
            "type": "transcript.partial",
            "text": "done",
            "is_final": True,
            "speech_final": True,
            "start": 1.1,
            "duration": 0.4,
        },
    )

    assert event == {
        "event": "UtteranceFinal",
        "timestamp": 1.5,
        "p_eot": 1.0,
        "transcript": "done",
        "start": 1.1,
        "duration": 0.4,
    }


def test_xai_defaults_and_key(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
    adapter = XAIStreamingSTTAdapter()

    assert adapter.adapter_id == "xai/stt-streaming"
    assert adapter.display_name == "xAI STT"
    assert not hasattr(adapter, "score_point")
    assert adapter.supports_language("ko")
    assert not adapter.supports_language("zh")
    assert resolve_api_key("XAI_API_KEY") == "xai-test-key"
    params = adapter._connection_params(language="es")
    assert params["endpointing"] == "10"
    assert params["language"] == "es"


def test_openai_realtime_speech_stopped_event_uses_audio_end_ms():
    event = _openai_speech_stopped_event(
        {
            "type": "input_audio_buffer.speech_stopped",
            "audio_start_ms": 420,
            "audio_end_ms": 1337,
            "item_id": "item_123",
        },
    )

    assert event == {
        "event": "SpeechStopped",
        "timestamp": 1.337,
        "p_eot": 1.0,
        "audio_end_ms": 1337,
        "audio_start_ms": 420,
        "item_id": "item_123",
    }


def test_openai_realtime_defaults_and_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    adapter = OpenAIRealtime2Adapter()

    assert adapter.adapter_id == "openai/gpt-realtime-2/semantic_vad_auto"
    assert adapter.display_name == "OpenAI GPT Realtime 2"
    assert not hasattr(adapter, "score_point")
    assert adapter.supports_language("zh")
    assert resolve_api_key("OPENAI_API_KEY") == "openai-test-key"
    session = adapter._session_update()["session"]
    assert session["audio"]["input"]["format"] == {
        "type": "audio/pcm",
        "rate": 24000,
    }
    assert session["audio"]["input"]["turn_detection"] == {
        "type": "semantic_vad",
        "eagerness": "auto",
        "create_response": False,
        "interrupt_response": False,
    }


def test_missing_api_key_error(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="XAI_API_KEY"):
        resolve_api_key("XAI_API_KEY")
