from __future__ import annotations

import numpy as np
import pytest
from datasets import Dataset

from eot_harness.io import (
    DEFAULT_INFERENCE_INTERVAL,
    DEFAULT_TRANSCRIPT_LAG,
    build_span_set,
    build_messages,
    iter_batches,
    transform_row,
)


def _row(**overrides):
    row = {
        "id": "turn-1",
        "language": "en",
        "audio": {
            "array": np.zeros(100, dtype=np.float32),
            "sampling_rate": 10,
        },
        "silence_spans": [
            {"start": 2.0, "end": 3.0},
            {"start": 4.0, "end": 10.0},
        ],
        "messages": [
            {"role": "assistant", "content": "How can I help?"},
            {"role": "user", "content": "I need to change an order."},
        ],
        "words": [
            {"word": "hello", "start": 1.1, "end": 1.4},
            {"word": "there", "start": 1.5, "end": 1.9},
            {"word": "again", "start": 3.1, "end": 3.4},
        ],
    }
    row.update(overrides)
    return row


def test_build_messages_appends_partial_user_transcript_to_existing_history():
    messages = build_messages(_row(), timestamp=2.0, transcript_lag=DEFAULT_TRANSCRIPT_LAG)
    assert messages == [
        {"role": "assistant", "content": "How can I help?"},
        {"role": "user", "content": "I need to change an order."},
        {"role": "user", "content": "hello"},
    ]


def test_transform_row_creates_prepared_prediction_points():
    rows = transform_row(_row(), inference_interval=0.5, transcript_lag=0.0)
    first = rows[0]

    assert first["id"] == "turn-1"
    assert first["language"] == "en"
    assert first["span_index"] == 0
    assert first["timestamp"] == 2.0
    assert first["silence_dur"] == 0.0
    assert first["label"] == "hold"
    assert first["audio"]["sampling_rate"] == 10
    assert first["audio"]["array"].shape[0] == 20
    assert first["messages"] == [
        {"role": "assistant", "content": "How can I help?"},
        {"role": "user", "content": "I need to change an order."},
        {"role": "user", "content": "hello there"},
    ]


def test_transform_row_accepts_minimal_audio_schema_without_text_fields():
    row = _row()
    row.pop("messages")
    row.pop("words")

    rows = transform_row(row, inference_interval=0.5, transcript_lag=0.0)

    assert rows
    assert rows[0]["messages"] == []


def test_iter_batches_groups_transformed_rows_for_adapter_inference():
    ds = Dataset.from_list([_row()])
    batches = list(
        iter_batches(
            ds,
            batch_size=3,
            inference_interval=0.5,
            transcript_lag=0.5,
        ),
    )

    first_meta, first_inputs = batches[0]
    assert len(first_meta) == 3
    assert len(first_inputs) == 3
    assert first_meta[0] == {
        "id": "turn-1",
        "language": "en",
        "span_index": 0,
        "timestamp": 2.0,
        "silence_dur": 0.0,
        "label": "hold",
    }
    assert list(first_inputs[0].keys()) == ["language", "audio", "messages"]
    assert first_inputs[0]["language"] == "en"


def test_iter_batches_can_limit_audio_prefix_context():
    row = _row(
        audio={
            "array": np.arange(100, dtype=np.float32),
            "sampling_rate": 10,
        },
    )
    ds = Dataset.from_list([row])

    batches = list(
        iter_batches(
            ds,
            batch_size=2,
            inference_interval=0.5,
            transcript_lag=0.0,
            max_audio_sec=1.0,
        ),
    )

    first_meta, first_inputs = batches[0]
    assert first_meta[0]["timestamp"] == 2.0
    np.testing.assert_array_equal(first_inputs[0]["audio"]["array"], np.arange(10, 20, dtype=np.float32))
    assert first_meta[1]["timestamp"] == 2.5
    np.testing.assert_array_equal(first_inputs[1]["audio"]["array"], np.arange(15, 25, dtype=np.float32))


def test_transform_row_skips_short_silence_spans():
    row = _row(
        silence_spans=[
            {"start": 2.0, "end": 2.09},
            {"start": 4.0, "end": 4.3},
        ],
    )
    rows = transform_row(row, inference_interval=0.1, transcript_lag=0.0)
    assert {entry["span_index"] for entry in rows} == {1}
    assert all(entry["label"] == "eot" for entry in rows)


def test_min_silence_span_controls_prediction_span_set():
    row = _row(
        silence_spans=[
            {"start": 2.0, "end": 2.3},
            {"start": 4.0, "end": 4.8},
        ],
    )

    rows = transform_row(row, inference_interval=0.1, transcript_lag=0.0, min_silence_span=0.5)
    span_set = build_span_set(Dataset.from_list([row]), min_silence_span=0.5)

    assert {entry["span_index"] for entry in rows} == {1}
    assert [(entry["id"], entry["language"], entry["span_index"]) for entry in span_set] == [("turn-1", "en", 1)]


def test_explicit_span_labels_override_last_span_rule():
    row = _row(
        cohort="short_turns",
        silence_spans=[{"start": 2.0, "end": 3.0, "label": "hold"}],
    )

    rows = transform_row(row, inference_interval=0.5, transcript_lag=0.0)
    span_set = build_span_set(Dataset.from_list([row]))

    assert {entry["label"] for entry in rows} == {"hold"}
    assert [(entry["label"], entry["cohort"]) for entry in span_set] == [("hold", "short_turns")]


def test_unlabeled_spans_keep_last_span_rule():
    span_set = build_span_set(Dataset.from_list([_row()]))

    assert [entry["label"] for entry in span_set] == ["hold", "eot"]
    assert "cohort" not in span_set[0]


def test_unknown_span_label_is_rejected():
    row = _row(silence_spans=[{"start": 2.0, "end": 3.0, "label": "maybe"}])

    with pytest.raises(ValueError, match="Silence span label"):
        build_span_set([row])
