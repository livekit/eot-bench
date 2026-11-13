from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pandas as pd
import pytest

from eot_harness.cli import _run_compare_models
from eot_harness.comparison import _vad_cutoff_at_latency_budget, _vad_latency_at_cutoff_budget


def _write_model_metrics(
    span_set_dir: Path,
    run_name: str,
    *,
    auc: float | None,
    ap: float | None,
    lat_at_5pct: float,
    lat_at_10pct: float,
    display_name: str | None = None,
    min_hold_span_duration: float = 0.2,
    max_hold_span_duration: float = 5.0,
) -> None:
    run_dir = span_set_dir / run_name
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True)
    manifest = {"adapter_id": run_name}
    if display_name is not None:
        manifest["display_name"] = display_name
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    tradeoff = pd.DataFrame(
        [
            {
                "policy_type": "model",
                "threshold": 0.5,
                "action_delay": 0.3,
                "timeout": 1.0,
                "score_point_s": 0.2,
                "cutoff_rate": 0.04,
                "mean_latency": lat_at_5pct,
                "timeout_rate": 0.1,
                "detect_rate": 0.9,
                "f1": 0.9,
                "n_hold_spans": 10,
                "n_eot_spans": 5,
                "is_pareto": True,
            },
            {
                "policy_type": "model",
                "threshold": 0.4,
                "action_delay": 0.5,
                "timeout": 1.0,
                "score_point_s": 0.2,
                "cutoff_rate": 0.08,
                "mean_latency": lat_at_10pct,
                "timeout_rate": 0.2,
                "detect_rate": 0.8,
                "f1": 0.85,
                "n_hold_spans": 10,
                "n_eot_spans": 5,
                "is_pareto": True,
            },
            {
                "policy_type": "vad",
                "threshold": float("nan"),
                "action_delay": 0.5,
                "timeout": 0.5,
                "score_point_s": float("nan"),
                "cutoff_rate": 0.04,
                "mean_latency": 0.7,
                "timeout_rate": 0.0,
                "detect_rate": 1.0,
                "f1": 0.7,
                "n_hold_spans": 10,
                "n_eot_spans": 5,
                "is_pareto": False,
            },
        ],
    )
    tradeoff.to_parquet(metrics_dir / "tradeoff.parquet", index=False)
    summary = {
        "n_spans": 15,
        "score_point_s": 0.2,
        "min_hold_span_duration": min_hold_span_duration,
        "max_hold_span_duration": max_hold_span_duration,
        "mean_frontier_latency_0_10": 0.7,
    }
    if auc is not None:
        summary["auc"] = auc
    if ap is not None:
        summary["ap"] = ap
    (metrics_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")


def _write_span_set(span_set_dir: Path) -> None:
    pd.DataFrame(
        [
            {"id": "hold-1", "language": "en", "span_index": 0, "label": "hold", "start": 0.0, "end": 0.25, "duration": 0.25},
            {"id": "hold-2", "language": "en", "span_index": 0, "label": "hold", "start": 0.0, "end": 0.45, "duration": 0.45},
            {"id": "hold-3", "language": "en", "span_index": 0, "label": "hold", "start": 0.0, "end": 0.65, "duration": 0.65},
            {"id": "hold-4", "language": "en", "span_index": 0, "label": "hold", "start": 0.0, "end": 1.2, "duration": 1.2},
            {"id": "hold-5", "language": "en", "span_index": 0, "label": "hold", "start": 0.0, "end": 2.1, "duration": 2.1},
            {"id": "eot-1", "language": "en", "span_index": 0, "label": "eot", "start": 0.0, "end": 0.5, "duration": 0.5},
        ],
    ).to_parquet(span_set_dir / "span_set.parquet", index=False)


def test_compare_models_writes_report_and_orders_by_latency_at_5pct_cutoff(tmp_path: Path) -> None:
    span_set_dir = tmp_path / "livekit__eot-bench-data__panels_eval_small__validation__min_silence_100ms"
    span_set_dir.mkdir(parents=True)
    _write_span_set(span_set_dir)
    _write_model_metrics(
        span_set_dir,
        "alpha_adapter__1111111111",
        auc=0.82,
        ap=0.7,
        lat_at_5pct=0.5,
        lat_at_10pct=0.3,
        display_name="Alpha",
    )
    _write_model_metrics(
        span_set_dir,
        "beta_adapter__2222222222",
        auc=0.91,
        ap=0.8,
        lat_at_5pct=0.8,
        lat_at_10pct=0.4,
        display_name="Beta",
    )
    stale_output_dir = span_set_dir / "comparison"
    stale_output_dir.mkdir()
    (stale_output_dir / "summary.json").write_text("{}", encoding="utf-8")
    (stale_output_dir / "report.html").write_text("old report", encoding="utf-8")
    (stale_output_dir / "metrics.png").write_bytes(b"old")
    (stale_output_dir / "classification_curve.png").write_bytes(b"old")
    (stale_output_dir / "cutoff_budget_compare_5_15pct.png").write_bytes(b"old")
    (stale_output_dir / "latency_budget_compare_400_600ms.png").write_bytes(b"old")
    pd.DataFrame([{"old": 1}]).to_parquet(stale_output_dir / "combined_tradeoff.parquet", index=False)

    output_dir = _run_compare_models(
        Namespace(
            span_set_dir=str(span_set_dir),
            min_hold_span_duration=0.2,
            max_hold_span_duration=5.0,
        ),
    )

    assert output_dir == span_set_dir / "comparison"
    expected_plots = [
        "pareto_frontier.png",
        "cutoff_rate_at_latency_budget_300_600ms.png",
        "latency_at_cutoff_budget_5_10pct.png",
    ]
    for filename in expected_plots:
        assert (output_dir / filename).exists()
    assert (output_dir / "report.md").exists()
    assert not (output_dir / "report.html").exists()
    assert not list(output_dir.glob("*.parquet"))
    assert not list(output_dir.glob("*.json"))
    assert not (output_dir / "metrics.png").exists()
    assert not (output_dir / "cutoff_budget_compare_5_15pct.png").exists()
    assert not (output_dir / "latency_budget_compare_400_600ms.png").exists()

    section_order = [
        "Pareto Frontier",
        "Best Cutoff Rate at Latency Budget",
        "Best Latency at Cutoff Budget",
        "Operating Points",
    ]

    report_markdown = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "Beta" in report_markdown
    assert [report_markdown.index(section) for section in section_order] == sorted(
        report_markdown.index(section) for section in section_order
    )
    assert report_markdown.index("| Cutoff | 5.0% | Alpha |") < report_markdown.index("| Cutoff | 5.0% | Beta |")
    assert "| Type | Budget | Model | Mean Latency | Cutoff | Detect | Threshold | Action Delay | Timeout |" in report_markdown
    assert "| Model | Best cutoff rate @ 0.3s latency | Best cutoff rate @ 0.6s latency |" in report_markdown
    assert "| Alpha | **8.0%** | **4.0%** |" in report_markdown
    assert "| VAD baseline | 80.0% | 60.0% |" in report_markdown
    assert "| Model | Best mean latency @ 5% cutoff | Best mean latency @ 10% cutoff |" in report_markdown
    assert "| Alpha | **500 ms** | **300 ms** |" in report_markdown
    assert "| VAD baseline | 2100 ms | 2100 ms |" in report_markdown
    assert "![Best cutoff rate at latency budgets](cutoff_rate_at_latency_budget_300_600ms.png)" in report_markdown
    assert "![Best latency at cutoff budgets](latency_at_cutoff_budget_5_10pct.png)" in report_markdown
    assert "| Model | Spans | lat@5 | lat@10 |" not in report_markdown
    assert "AUC" not in report_markdown
    assert "classification_curve.png" not in report_markdown


def test_compare_models_does_not_require_auc_ap_summary_keys(tmp_path: Path) -> None:
    span_set_dir = tmp_path / "span-set"
    _write_model_metrics(
        span_set_dir,
        "alpha_adapter__1111111111",
        auc=None,
        ap=None,
        lat_at_5pct=0.5,
        lat_at_10pct=0.3,
        display_name="Alpha",
    )

    output_dir = _run_compare_models(
        Namespace(
            span_set_dir=str(span_set_dir),
            min_hold_span_duration=0.2,
            max_hold_span_duration=5.0,
        ),
    )

    report_markdown = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "Pareto Frontier" in report_markdown
    assert "AUC" not in report_markdown


def test_vad_baseline_operating_point_helpers() -> None:
    vad = pd.DataFrame(
        [
            {"mean_latency": 0.3, "cutoff_rate": 0.25},
            {"mean_latency": 0.6, "cutoff_rate": 0.12},
            {"mean_latency": 1.0, "cutoff_rate": 0.08},
            {"mean_latency": 2.0, "cutoff_rate": 0.04},
        ],
    )

    assert _vad_cutoff_at_latency_budget(vad, 0.6) == 0.12
    assert _vad_cutoff_at_latency_budget(vad, 0.5) == 0.25
    assert _vad_cutoff_at_latency_budget(vad, 0.2) is None
    assert _vad_latency_at_cutoff_budget(vad, 0.10) == 1.0
    assert _vad_latency_at_cutoff_budget(vad, 0.05) == 2.0
    assert _vad_latency_at_cutoff_budget(vad, 0.03) is None


def test_compare_models_rejects_mismatched_metric_duration(tmp_path: Path) -> None:
    span_set_dir = tmp_path / "span-set"
    _write_model_metrics(
        span_set_dir,
        "alpha_adapter__1111111111",
        auc=0.82,
        ap=0.7,
        lat_at_5pct=0.5,
        lat_at_10pct=0.3,
        min_hold_span_duration=0.1,
    )

    with pytest.raises(ValueError, match="min_hold_span_duration"):
        _run_compare_models(
            Namespace(
                span_set_dir=str(span_set_dir),
                min_hold_span_duration=0.2,
                max_hold_span_duration=5.0,
            ),
        )


def test_cohort_sections_report_each_cohort(tmp_path: Path) -> None:
    from eot_harness.comparison import ModelMetrics, _cohort_sections

    span_rows, prediction_rows = [], []
    for cohort, n_turns in (("general", 6), ("short_turns", 6)):
        for turn in range(n_turns):
            turn_id = f"{cohort}-{turn}"
            # Even short-turn rows end in a pause, so they have no eot span.
            labels = ["hold"] if cohort == "short_turns" and turn % 2 == 0 else ["hold", "eot"]
            if cohort == "short_turns" and turn % 2 == 1:
                labels = ["eot"]
            for span_index, label in enumerate(labels):
                duration = 0.5 if label == "hold" else 1.5
                span_rows.append(
                    {"id": turn_id, "span_index": span_index, "label": label, "duration": duration, "cohort": cohort},
                )
                for step in range(int(round(duration / 0.1)) + 1):
                    prediction_rows.append(
                        {
                            "id": turn_id,
                            "span_index": span_index,
                            "timestamp": round(step * 0.1, 6),
                            "silence_dur": round(step * 0.1, 6),
                            "p_eot": 0.9 if label == "eot" else 0.1,
                            "label": label,
                        },
                    )
    run_dir = tmp_path / "model_a"
    run_dir.mkdir()
    pd.DataFrame(span_rows).to_parquet(tmp_path / "span_set.parquet", index=False)
    pd.DataFrame(prediction_rows).to_parquet(run_dir / "predictions.parquet", index=False)
    model = ModelMetrics(
        name="Model A",
        run_dir=run_dir,
        metrics_dir=run_dir,
        manifest={},
        summary={"score_point_s": 0.2},
        tradeoff=pd.DataFrame(),
    )

    report = _cohort_sections(tmp_path, [model], min_hold_span_duration=0.2, max_hold_span_duration=5.0)

    assert "### `general`\n\n6 rows, 6 hold spans, 6 eot spans." in report
    assert "### `short_turns`\n\n6 rows, 3 hold spans, 3 eot spans." in report
    assert report.count("| Model A |") == 2

    pd.DataFrame(span_rows).drop(columns="cohort").to_parquet(tmp_path / "span_set.parquet", index=False)
    assert _cohort_sections(tmp_path, [model], min_hold_span_duration=0.2, max_hold_span_duration=5.0) == ""
