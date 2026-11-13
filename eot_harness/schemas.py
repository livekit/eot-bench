"""Public schema constants for the EoT harness.

This module intentionally avoids exporting a large tree of Python types.
The public contract should stay simple:

- datasets provide a few required columns
- predictions.parquet provides a few required columns
- runtime validation enforces the contract
"""

DATASET_REQUIRED_FIELDS = (
    "id",
    "language",
    "audio",
    "silence_spans",
)

DATASET_OPTIONAL_FIELDS = (
    "messages",
    "words",
    "cohort",
)

# Optional key on each `silence_spans` entry. Its value is a prediction label.
# Without it, the last span of a row is `eot` and every earlier span is `hold`.
SILENCE_SPAN_LABEL_FIELD = "label"

PREDICTION_REQUIRED_COLUMNS = (
    "id",
    "language",
    "span_index",
    "timestamp",
    "silence_dur",
    "p_eot",
    "label",
)

PREDICTION_LABELS = (
    "hold",
    "eot",
)
