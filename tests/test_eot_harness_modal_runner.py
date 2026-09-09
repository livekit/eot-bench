from __future__ import annotations

import json
from pathlib import Path

import pytest

from eot_harness.modal_runner import (
    _predict_namespace,
    _read_prediction_payload,
    _select_remote_preset,
    _write_prediction_payload,
)


def test_predict_namespace_uses_harness_predict_defaults(tmp_path: Path) -> None:
    args = _predict_namespace(
        {
            "path": "livekit/eot-bench-data",
            "name": "all",
            "adapter": "eot_harness.livekit_turn_detector_mini_adapter:LiveKitTurnDetectorMiniAdapter",
        },
        tmp_path,
    )

    assert args.path == "livekit/eot-bench-data"
    assert args.name == "all"
    assert args.repo_id == "livekit/eot-bench-data"
    assert args.subset == "all"
    assert args.split == "validation"
    assert args.revision is None
    assert args.output_dir == str(tmp_path)
    assert args.min_silence_span == 0.1
    assert args.batch_size == 128
    assert args.inference_interval == 0.1
    assert args.transcript_lag == 0.5
    assert args.overwrite is False


def test_predict_namespace_requires_core_prediction_config(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing required keys"):
        _predict_namespace({"path": "livekit/eot-bench-data"}, tmp_path)


def test_prediction_payload_roundtrip(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_dir = source_root / "span-set" / "model-run"
    source_dir.mkdir(parents=True)
    (source_dir / "predictions.parquet").write_bytes(b"parquet-bytes")
    (source_dir / "manifest.json").write_text(
        json.dumps({"n_rows": 3}), encoding="utf-8"
    )
    (source_dir.parent / "span_set.parquet").write_bytes(b"span-set-bytes")
    (source_dir.parent / "span_set_manifest.json").write_text(
        json.dumps({"n_spans": 2}), encoding="utf-8"
    )

    payload = _read_prediction_payload(source_root, [source_dir])
    output_dir = tmp_path / "output"
    run_dir = _write_prediction_payload(payload, output_dir)[0]

    assert run_dir == output_dir / "span-set" / "model-run"
    assert payload["runs"][0]["relative_output_dir"] == "span-set/model-run"
    assert (run_dir / "predictions.parquet").read_bytes() == b"parquet-bytes"
    assert json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")) == {
        "n_rows": 3
    }
    assert (run_dir.parent / "span_set.parquet").read_bytes() == b"span-set-bytes"
    assert json.loads(
        (run_dir.parent / "span_set_manifest.json").read_text(encoding="utf-8")
    ) == {"n_spans": 2}


def test_read_prediction_payload_requires_both_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "span-set" / "model-run"
    run_dir.mkdir(parents=True)
    (run_dir / "predictions.parquet").write_bytes(b"parquet-bytes")

    with pytest.raises(RuntimeError, match="required artifacts"):
        _read_prediction_payload(tmp_path, run_dir)


def test_select_remote_preset_honors_config_override() -> None:
    assert _select_remote_preset({}, "default") == "default"
    assert _select_remote_preset({"modal_preset": "audio"}, "default") == "audio"
    assert _select_remote_preset({"modal_preset": "vap"}, "default") == "vap"

    with pytest.raises(ValueError, match="unknown Modal preset"):
        _select_remote_preset({}, "missing")
