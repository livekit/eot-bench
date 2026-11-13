from __future__ import annotations

import pytest

from eot_harness.deepgram_flux_adapter import (
    DeepgramFluxStreamingAdapter,
    _resolve_deepgram_api_key,
    build_flux_prediction_rows,
)


def _row():
    return {
        "id": "turn-1",
        "silence_spans": [
            {"start": 1.0, "end": 1.4},
            {"start": 2.0, "end": 2.3},
        ],
    }


def test_build_flux_prediction_rows_forwards_latest_turn_confidence():
    rows = build_flux_prediction_rows(
        _row(),
        [
            {"event": "Ignored", "audio_window_end": None, "end_of_turn_confidence": None},
            {"event": "Update", "audio_window_end": 0.9, "end_of_turn_confidence": 0.12},
            {"event": "Update", "audio_window_end": 1.25, "end_of_turn_confidence": 0.44},
            {"event": "Update", "audio_window_end": 2.2, "end_of_turn_confidence": 0.82},
        ],
        inference_interval=0.2,
    )

    assert [row["timestamp"] for row in rows] == [1.0, 1.2, 1.4, 2.0, 2.2, 2.3]
    assert [row["span_index"] for row in rows] == [0, 0, 0, 1, 1, 1]
    assert [row["label"] for row in rows] == ["hold", "hold", "hold", "eot", "eot", "eot"]
    assert [row["p_eot"] for row in rows] == [0.12, 0.12, 0.44, 0.44, 0.82, 0.82]


def test_build_flux_prediction_rows_requires_usable_confidence_events():
    with pytest.raises(RuntimeError, match="No usable Flux confidence events"):
        build_flux_prediction_rows(
            _row(),
            [{"event": "Update", "audio_window_end": None, "end_of_turn_confidence": None}],
            inference_interval=0.2,
        )


def test_flux_multilingual_language_handling_is_strict():
    adapter = DeepgramFluxStreamingAdapter(model="flux-general-multi")
    assert not hasattr(adapter, "score_point")
    assert adapter.display_name == "Deepgram Flux"
    assert adapter.supports_language("ja")
    assert not adapter.supports_language("ko")
    assert adapter._language_hint_or_skip({"id": "ok", "language": "EN"}) == ("en", None)

    with pytest.raises(RuntimeError, match="Unsupported language"):
        adapter._language_hint_or_skip({"id": "bad", "language": "ko"})

    skip_adapter = DeepgramFluxStreamingAdapter(
        model="flux-general-multi",
        skip_unsupported_languages=True,
    )
    language_hint, skip_row = skip_adapter._language_hint_or_skip({"id": "bad", "language": "ko"})
    assert language_hint is None
    assert skip_row == {
        "id": "bad",
        "skipped": True,
        "language": "ko",
        "reason": "unsupported_language",
        "events": [],
        "prediction_rows": [],
        "audio_sec": 0.0,
    }


def test_deepgram_key_uses_canonical_env(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test-key")

    assert _resolve_deepgram_api_key() == "dg-test-key"


def test_flux_close_timeout_is_retried(monkeypatch):
    import asyncio

    from eot_harness import deepgram_flux_adapter as module

    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test-key")

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    adapter = DeepgramFluxStreamingAdapter(max_retries=2)
    calls = []

    async def replay(row, api_key, **kwargs):
        calls.append(row["id"])
        if len(calls) < 3:
            raise module._FluxCloseTimeout("no close")
        return {"id": row["id"]}

    monkeypatch.setattr(adapter, "_replay_turn", replay)
    row = {**_row(), "language": "en"}

    assert asyncio.run(adapter.predict_turn(row)) == {"id": "turn-1"}
    assert len(calls) == 3

    calls.clear()
    adapter.max_retries = 1
    with pytest.raises(module._FluxCloseTimeout):
        asyncio.run(adapter.predict_turn(row))
