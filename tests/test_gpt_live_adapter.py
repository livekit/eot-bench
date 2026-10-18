from __future__ import annotations

import numpy as np
import pytest

from eot_harness.cli import _streaming_model_run_dir_name
from eot_harness.gpt_live_adapter import (
    GPTLiveAdapter,
    OutputSpeechTracker,
    score_output_utterances,
    turn_taking_summary,
    voiced_segments,
)


def _row():
    return {
        "id": "turn-1",
        "silence_spans": [
            {"start": 2.0, "end": 2.6},
            {"start": 5.0, "end": 6.5},
        ],
    }


def _speech(start, end, voiced=None):
    return {"event": "OutputSpeech", "timestamp": start, "end": end, "voiced_sec": end - start if voiced is None else voiced}


def _pcm(seconds: float, amplitude: float, sample_rate: int = 24000) -> bytes:
    return (np.full(round(seconds * sample_rate), amplitude) * 32767).astype("<i2").tobytes()


def test_voiced_segments_bridges_short_gaps_only():
    voiced = [True, True, False, True] + [False] * 20 + [True]

    segments = voiced_segments(voiced, frame_sec=0.01, max_gap_s=0.1)

    assert [(round(s, 2), round(e, 2), round(v, 2)) for s, e, v in segments] == [
        (0.0, 0.04, 0.03),
        (0.24, 0.25, 0.01),
    ]


def test_tracker_anchors_segments_to_the_input_audio_clock():
    tracker = OutputSpeechTracker()
    # 1 s of silence, then 0.5 s of speech; the second chunk arrives late, so the first anchors the clock.
    tracker.add(_pcm(1.0, 0.0), received_at=11.0)
    tracker.add(_pcm(0.5, 0.1), received_at=11.9)

    assert tracker.stream_start == pytest.approx(10.0)
    assert tracker.segments(audio_start=9.0) == [
        {"event": "OutputSpeech", "timestamp": 2.0, "end": 2.5, "voiced_sec": 0.5},
    ]


def test_tracker_ignores_the_connect_tick():
    tracker = OutputSpeechTracker()
    tracker.add(_pcm(0.05, 0.1) + _pcm(0.95, 0.0), received_at=1.0)

    assert tracker.segments(audio_start=0.0) == []


def test_utterance_inside_a_span_is_a_floor_at_its_onset():
    [event] = score_output_utterances(_row(), [_speech(5.3, 5.8)], voiced_cap_s=2.0)

    assert event["event"] == "OutputUtterance"
    assert event["kind"] == "floor"
    assert event["timestamp"] == 5.3
    assert event["p_eot"] == 0.25
    assert event["overlap_sec"] == 0.0


def test_utterance_running_into_a_pause_counts_at_the_pause_start():
    [event] = score_output_utterances(_row(), [_speech(3.8, 8.0)])

    assert event["kind"] == "floor"
    assert event["timestamp"] == 5.0
    assert event["onset"] == 3.8
    assert event["overlap_sec"] == 1.2
    assert event["p_eot"] == 1.0


def test_utterance_inside_user_speech_is_a_backchannel_when_the_model_speaks_again():
    events = score_output_utterances(_row(), [_speech(3.0, 3.4), _speech(5.2, 6.0)])

    assert [(e["kind"], e["p_eot"]) for e in events] == [("backchannel", None), ("floor", 0.4)]


def test_last_utterance_inside_user_speech_is_an_interruption():
    events = score_output_utterances(_row(), [_speech(2.1, 2.4), _speech(3.0, 4.5)])

    assert [(e["kind"], e["p_eot"]) for e in events] == [("floor", 0.15), ("interruption", None)]


def test_utterance_after_the_audio_is_a_floor():
    [event] = score_output_utterances(_row(), [_speech(7.0, 8.0)])

    assert event["kind"] == "floor"
    assert event["timestamp"] == 7.0


def test_segments_merge_across_short_gaps_into_one_utterance():
    events = score_output_utterances(
        _row(),
        [_speech(2.1, 2.4), _speech(2.7, 3.0), _speech(5.2, 5.5)],
        merge_gap_s=0.4,
    )

    assert [(e["timestamp"], e["voiced_sec"]) for e in events] == [(2.1, 0.6), (5.2, 0.3)]


def test_turn_taking_summary_keeps_the_signed_reply_offset():
    utterances = score_output_utterances(_row(), [_speech(3.0, 3.4), _speech(4.6, 6.0)])

    assert turn_taking_summary(_row(), utterances) == {
        "id": "turn-1",
        "interrupted": False,
        "reply_offset_sec": -0.4,
    }


def test_turn_taking_summary_reports_an_interruption_without_a_reply():
    utterances = score_output_utterances(_row(), [_speech(3.0, 4.5)])

    assert turn_taking_summary(_row(), utterances) == {
        "id": "turn-1",
        "interrupted": True,
        "reply_offset_sec": None,
    }


def test_adapter_defaults_and_session_start():
    adapter = GPTLiveAdapter()

    assert adapter.adapter_id == "livekit-inference/openai/gpt-live-1"
    assert adapter.display_name == "OpenAI GPT-Live"
    assert adapter.supports_language("ja")
    session = adapter._session_start()["session"]
    assert session["model"] == "openai/gpt-live-1"
    assert session["audio"] == {"format": {"type": "audio/pcm", "rate": 24000}, "output": {"voice": "marin"}}
    assert session["delegation"] == {"type": "client"}
    assert _streaming_model_run_dir_name("eot_harness.gpt_live_adapter:GPTLiveAdapter", adapter) == (
        "gpt_live_adapter__gpt_live_1"
    )


@pytest.mark.parametrize(
    "kwargs",
    [{"merge_gap_s": 0.05}, {"voiced_cap_s": 0}, {"concurrency": 0}],
)
def test_adapter_rejects_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        GPTLiveAdapter(**kwargs)
