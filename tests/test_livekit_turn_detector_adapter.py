from __future__ import annotations

import inspect

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
