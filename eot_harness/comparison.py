from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .metrics import get_pareto_operating_points, pareto_frontier

_CACHE_DIR = (Path(__file__).resolve().parent.parent / ".cache" / "eot_harness").resolve()
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE_DIR))
os.environ.setdefault("MPLCONFIGDIR", str(_CACHE_DIR / "matplotlib"))

import matplotlib.pyplot as plt
from matplotlib import ticker
import seaborn as sns

EPS = 1e-9
LATENCY_BUDGET_COMPARISON = (0.3, 0.6)
CUTOFF_BUDGET_COMPARISON = (0.05, 0.10)
VAD_BASELINE_TABLE_STEP = 0.01
LANGUAGE_OPERATING_POINT_METRICS = (
    {
        "key": "best_cutoff_rate_at_0_3s_latency",
        "title": "Best cutoff rate @ 0.3s latency",
        "value_type": "rate",
    },
    {
        "key": "best_cutoff_rate_at_0_6s_latency",
        "title": "Best cutoff rate @ 0.6s latency",
        "value_type": "rate",
    },
    {
        "key": "best_mean_latency_at_5pct_cutoff",
        "title": "Best mean latency @ 5% cutoff",
        "value_type": "latency",
    },
    {
        "key": "best_mean_latency_at_10pct_cutoff",
        "title": "Best mean latency @ 10% cutoff",
        "value_type": "latency",
    },
)
REPORT_PLOTS = (
    "pareto_frontier.png",
    "cutoff_rate_at_latency_budget_300_600ms.png",
    "latency_at_cutoff_budget_5_10pct.png",
)
STALE_REPORT_PLOTS = {
    "metrics.png",
    "classification_curve.png",
    "cutoff_budget_compare_5_15pct.png",
    "latency_budget_compare_400_600ms.png",
    "latency_budget_300ms.png",
    "latency_budget_500ms.png",
    "latency_budget_700ms.png",
    "cutoff_budget_5pct.png",
    "cutoff_budget_10pct.png",
    "cutoff_budget_15pct.png",
    "cutoff_budget_20pct.png",
}
REPORT_DATA_ARTIFACT_PATTERNS = ("*.parquet", "*.json")
LANGUAGE_DISPLAY_ORDER = ("en", "pt", "es", "de", "hi", "fr", "ja", "id", "nl", "it", "tr", "ar", "zh", "ko")
LANGUAGE_DISPLAY_LABELS = {
    "en": "English",
    "pt": "Portuguese",
    "es": "Spanish",
    "de": "German",
    "hi": "Hindi",
    "fr": "French",
    "ja": "Japanese",
    "id": "Indonesian",
    "nl": "Dutch",
    "it": "Italian",
    "tr": "Turkish",
    "ar": "Arabic",
    "zh": "Chinese",
    "ko": "Korean",
}
MODEL_DISPLAY_ORDER = (
    "LiveKit Turn Detector v1",
    "LiveKit Turn Detector v1-mini",
    "Deepgram Flux",
    "ultraVAD",
    "SmartTurn v3.2",
    "haan (SmartTurn v3.2 phone-audio fine-tune)",
    "AssemblyAI",
    "Soniox",
    "xAI STT",
    "OpenAI GPT Realtime 2",
    "VAD baseline",
)


@dataclass(frozen=True)
class ModelMetrics:
    name: str
    run_dir: Path
    metrics_dir: Path
    manifest: dict[str, Any]
    summary: dict[str, Any]
    tradeoff: pd.DataFrame


def write_comparison_report(
    span_set_dir: str | Path,
    *,
    min_hold_span_duration: float,
    max_hold_span_duration: float,
) -> Path:
    span_set_dir = Path(span_set_dir).expanduser().resolve()
    if not span_set_dir.exists():
        raise FileNotFoundError(f"span set directory does not exist: {span_set_dir}")
    if not span_set_dir.is_dir():
        raise NotADirectoryError(f"span set path is not a directory: {span_set_dir}")

    models = _load_model_metrics(
        span_set_dir,
        min_hold_span_duration=min_hold_span_duration,
        max_hold_span_duration=max_hold_span_duration,
    )
    combined_tradeoff = _combined_tradeoff(models)
    latency_budget_values = sorted(LATENCY_BUDGET_COMPARISON)
    cutoff_budget_values = sorted(CUTOFF_BUDGET_COMPARISON)
    latency_budget_ops = get_pareto_operating_points(
        combined_tradeoff,
        "mean_latency",
        latency_budget_values,
    )
    cutoff_budget_ops = get_pareto_operating_points(
        combined_tradeoff,
        "cutoff_rate",
        cutoff_budget_values,
    )
    ordered_models = _order_models_by_latency_at_cutoff(
        models,
        cutoff_budget_ops,
        cutoff_budget=CUTOFF_BUDGET_COMPARISON[0],
    )
    model_order = [model.name for model in ordered_models]
    pareto = pareto_frontier(combined_tradeoff)
    vad_timeout_baseline = _vad_timeout_baseline(combined_tradeoff)
    vad_table_baseline = _fine_vad_baseline_from_span_set(
        span_set_dir,
        min_hold_span_duration=min_hold_span_duration,
        max_hold_span_duration=max_hold_span_duration,
        fallback=vad_timeout_baseline,
    )

    output_dir = span_set_dir / "comparison"
    output_dir.mkdir(parents=True, exist_ok=True)
    _remove_stale_report_artifacts(output_dir)

    colors = _model_colors(model_order)
    images = _make_plots(
        output_dir=output_dir,
        models=ordered_models,
        model_order=model_order,
        colors=colors,
        pareto=pareto,
        vad_timeout_baseline=vad_timeout_baseline,
        latency_budget_ops=latency_budget_ops,
        cutoff_budget_ops=cutoff_budget_ops,
    )
    _write_markdown(
        output_dir=output_dir,
        model_order=model_order,
        latency_budget_ops=latency_budget_ops,
        cutoff_budget_ops=cutoff_budget_ops,
        vad_table_baseline=vad_table_baseline,
        images=images,
    )
    return output_dir


def write_language_comparison_report(
    span_set_root: str | Path,
    *,
    min_hold_span_duration: float,
    max_hold_span_duration: float,
    output_dir: str | Path | None = None,
) -> Path:
    span_set_root = Path(span_set_root).expanduser().resolve()
    if not span_set_root.exists():
        raise FileNotFoundError(f"span set root does not exist: {span_set_root}")
    if not span_set_root.is_dir():
        raise NotADirectoryError(f"span set root path is not a directory: {span_set_root}")

    language_dirs = _discover_language_span_set_dirs(span_set_root)
    rows: list[dict[str, Any]] = []
    skipped_languages: list[dict[str, str]] = []
    for language, language_dir in language_dirs:
        try:
            models = _load_model_metrics(
                language_dir,
                min_hold_span_duration=min_hold_span_duration,
                max_hold_span_duration=max_hold_span_duration,
            )
        except FileNotFoundError as exc:
            skipped_languages.append({"language": language, "reason": str(exc)})
            continue

        combined_tradeoff = _combined_tradeoff(models)
        latency_budget_ops = get_pareto_operating_points(
            combined_tradeoff,
            "mean_latency",
            sorted(LATENCY_BUDGET_COMPARISON),
        )
        cutoff_budget_ops = get_pareto_operating_points(
            combined_tradeoff,
            "cutoff_rate",
            sorted(CUTOFF_BUDGET_COMPARISON),
        )
        metric_values = _language_operating_point_values(
            latency_budget_ops=latency_budget_ops,
            cutoff_budget_ops=cutoff_budget_ops,
        )

        for model in models:
            values = metric_values.get(model.name, {})
            rows.append(
                {
                    "language": language,
                    "model": model.name,
                    **{metric["key"]: _json_number(values.get(metric["key"])) for metric in LANGUAGE_OPERATING_POINT_METRICS},
                    "run_dir": str(model.run_dir.relative_to(span_set_root)),
                    "metrics_dir": str(model.metrics_dir.relative_to(span_set_root)),
                    "n_spans": model.summary.get("n_spans"),
                },
            )
        vad_table_baseline = _fine_vad_baseline_from_span_set(
            language_dir,
            min_hold_span_duration=min_hold_span_duration,
            max_hold_span_duration=max_hold_span_duration,
            fallback=_vad_timeout_baseline(combined_tradeoff),
        )
        rows.append(
            {
                "language": language,
                "model": "VAD baseline",
                **_language_vad_operating_point_values(vad_table_baseline),
                "run_dir": None,
                "metrics_dir": None,
                "n_spans": _language_span_count(language_dir),
            },
        )

    if not rows:
        raise FileNotFoundError(
            f"No model metric artifacts found under language directories in {span_set_root}.",
        )

    output_dir = Path(output_dir).expanduser().resolve() if output_dir else span_set_root / "language_comparison"
    output_dir.mkdir(parents=True, exist_ok=True)
    _remove_stale_language_report_artifacts(output_dir)

    df = pd.DataFrame(rows)
    languages = sorted(df["language"].dropna().astype(str).unique().tolist())
    models = _ordered_model_names(df["model"].dropna().astype(str).unique().tolist())
    matrices = {
        metric["key"]: (
            df.pivot_table(index="language", columns="model", values=metric["key"], aggfunc="first")
            .reindex(index=languages, columns=models)
            .astype(float)
        )
        for metric in LANGUAGE_OPERATING_POINT_METRICS
    }
    metric_configs = {metric["key"]: metric for metric in LANGUAGE_OPERATING_POINT_METRICS}
    heatmaps = {
        metric_key: _write_language_heatmap(
            matrix,
            metric_key=metric_key,
            title=str(metric_configs[metric_key]["title"]),
            value_type=str(metric_configs[metric_key]["value_type"]),
            output_dir=output_dir,
        )
        for metric, matrix in matrices.items()
        for metric_key in [metric]
    }
    df.to_parquet(output_dir / "metrics.parquet", index=False)
    summary = {
        "metrics": [str(metric["key"]) for metric in LANGUAGE_OPERATING_POINT_METRICS],
        "metric_titles": {str(metric["key"]): str(metric["title"]) for metric in LANGUAGE_OPERATING_POINT_METRICS},
        "span_set_root": str(span_set_root),
        "languages": languages,
        "models": models,
        "values": {metric: _matrix_values(matrix) for metric, matrix in matrices.items()},
        "rows": rows,
        "skipped_languages": skipped_languages,
        "artifacts": {
            "heatmaps": heatmaps,
            "metrics": "metrics.parquet",
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_language_markdown(output_dir=output_dir, heatmaps=heatmaps, matrices=matrices, metric_configs=metric_configs)
    return output_dir


def _discover_language_span_set_dirs(span_set_root: Path) -> list[tuple[str, Path]]:
    language_dirs = [
        (child.name, child)
        for child in sorted(span_set_root.iterdir())
        if child.is_dir() and (child / "span_set_manifest.json").exists()
    ]
    if not language_dirs:
        raise FileNotFoundError(
            f"No language span-set directories found under {span_set_root}; expected */span_set_manifest.json.",
        )
    return language_dirs


def _remove_stale_language_report_artifacts(output_dir: Path) -> None:
    (output_dir / "report.html").unlink(missing_ok=True)
    for path in output_dir.glob("heatmap_*.png"):
        path.unlink()


def _language_operating_point_values(
    *,
    latency_budget_ops: pd.DataFrame,
    cutoff_budget_ops: pd.DataFrame,
) -> dict[str, dict[str, float | None]]:
    latency_values = _metric_values_from_operating_points(
        latency_budget_ops,
        budget_column="mean_latency",
        budget_values=LATENCY_BUDGET_COMPARISON,
    )
    cutoff_values = _metric_values_from_operating_points(
        cutoff_budget_ops,
        budget_column="cutoff_rate",
        budget_values=CUTOFF_BUDGET_COMPARISON,
    )
    models = sorted({*latency_values.keys(), *cutoff_values.keys()})
    values: dict[str, dict[str, float | None]] = {}
    for model in models:
        latency_row = latency_values.get(model, [None] * len(LATENCY_BUDGET_COMPARISON))
        cutoff_row = cutoff_values.get(model, [None] * len(CUTOFF_BUDGET_COMPARISON))
        values[model] = {
            "best_cutoff_rate_at_0_3s_latency": latency_row[0] if len(latency_row) > 0 else None,
            "best_cutoff_rate_at_0_6s_latency": latency_row[1] if len(latency_row) > 1 else None,
            "best_mean_latency_at_5pct_cutoff": cutoff_row[0] if len(cutoff_row) > 0 else None,
            "best_mean_latency_at_10pct_cutoff": cutoff_row[1] if len(cutoff_row) > 1 else None,
        }
    return values


def _language_vad_operating_point_values(vad_table_baseline: pd.DataFrame) -> dict[str, float | None]:
    return {
        "best_cutoff_rate_at_0_3s_latency": _vad_cutoff_at_latency_budget(vad_table_baseline, 0.3),
        "best_cutoff_rate_at_0_6s_latency": _vad_cutoff_at_latency_budget(vad_table_baseline, 0.6),
        "best_mean_latency_at_5pct_cutoff": _vad_latency_at_cutoff_budget(vad_table_baseline, 0.05),
        "best_mean_latency_at_10pct_cutoff": _vad_latency_at_cutoff_budget(vad_table_baseline, 0.10),
    }


def _language_span_count(language_dir: Path) -> int | None:
    span_set_path = language_dir / "span_set.parquet"
    if not span_set_path.exists():
        return None
    try:
        return int(len(pd.read_parquet(span_set_path, columns=["label"])))
    except Exception:
        return None


def _write_language_heatmap(
    matrix: pd.DataFrame,
    *,
    metric_key: str,
    title: str,
    value_type: str,
    output_dir: Path,
) -> str:
    display_matrix = _language_display_matrix(matrix)
    heatmap_matrix = display_matrix * 100.0 if value_type == "rate" else display_matrix * 1000.0
    sns.set_theme(style="white", context="notebook")
    fig_width = max(9.0, min(18.0, 2.5 + 1.1 * max(1, len(display_matrix.columns))))
    fig_height = max(5.6, min(14.0, 1.2 + 0.42 * max(1, len(display_matrix.index))))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    cmap = sns.color_palette("mako_r", as_cmap=True)
    cmap.set_bad("#e5e7eb")
    finite_values = heatmap_matrix.to_numpy(dtype=float)
    finite_values = finite_values[np.isfinite(finite_values)]
    vmin = 0.0
    vmax = float(np.nanmax(finite_values)) if finite_values.size else 1.0
    if value_type == "rate":
        vmax = max(10.0, min(60.0, math.ceil(vmax / 10.0) * 10.0))
        cbar_label = "False cutoff rate (%)"
        fmt = ".1f"
    else:
        vmax = max(500.0, min(3000.0, math.ceil(vmax / 250.0) * 250.0))
        cbar_label = "Mean latency (ms)"
        fmt = ".0f"

    sns.heatmap(
        heatmap_matrix,
        ax=ax,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        annot=True,
        fmt=fmt,
        linewidths=0.6,
        linecolor="white",
        cbar_kws={"label": cbar_label},
        mask=heatmap_matrix.isna(),
    )
    ax.set_title(title, fontsize=14, pad=10)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", rotation=50, labelrotation=50, bottom=False, top=True, labelbottom=False, labeltop=True)
    for label in ax.get_xticklabels():
        label.set_horizontalalignment("left")
    ax.tick_params(axis="y", rotation=0)
    ax.set_facecolor("#e5e7eb")
    _set_heatmap_annotation_colors(ax, cmap=cmap, vmin=vmin, vmax=vmax)
    fig.tight_layout()

    return _save_fig(fig, output_dir / f"heatmap_{metric_key}.png")


def _ordered_model_names(models: list[str]) -> list[str]:
    vad_models = ["VAD baseline"] if "VAD baseline" in models else []
    known_models = [model for model in MODEL_DISPLAY_ORDER if model in models and model != "VAD baseline"]
    extra_models = sorted(model for model in models if model not in MODEL_DISPLAY_ORDER)
    return [*known_models, *extra_models, *vad_models]


def _language_display_matrix(matrix: pd.DataFrame) -> pd.DataFrame:
    known_languages = [language for language in LANGUAGE_DISPLAY_ORDER if language in matrix.index]
    extra_languages = [language for language in matrix.index if language not in LANGUAGE_DISPLAY_ORDER]
    ordered = matrix.reindex([*known_languages, *extra_languages])
    return ordered.rename(index=lambda language: LANGUAGE_DISPLAY_LABELS.get(str(language), str(language)))


def _set_heatmap_annotation_colors(ax, *, cmap, vmin: float, vmax: float) -> None:
    for text in ax.texts:
        try:
            value = float(text.get_text())
        except ValueError:
            continue
        normalized = min(1.0, max(0.0, (value - vmin) / max(vmax - vmin, EPS)))
        red, green, blue, _alpha = cmap(normalized)
        luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        text.set_color("white" if luminance < 0.5 else "#1f2937")


def _write_language_markdown(
    *,
    output_dir: Path,
    heatmaps: dict[str, str],
    matrices: dict[str, pd.DataFrame],
    metric_configs: dict[str, dict[str, str]],
) -> None:
    sections = []
    for metric in LANGUAGE_OPERATING_POINT_METRICS:
        metric_key = str(metric["key"])
        matrix = matrices[metric_key]
        heatmap = heatmaps[metric_key]
        title = str(metric_configs[metric_key]["title"])
        value_type = str(metric_configs[metric_key]["value_type"])
        sections.append(
            f"""## {title}

![{title} heatmap]({heatmap})

{_markdown_table(["Language", *matrix.columns.astype(str).tolist()], _language_matrix_rows(matrix, value_type=value_type))}
""",
        )
    markdown_doc = "# EoT Language Comparison\n\n" + "\n".join(sections)
    (output_dir / "report.md").write_text(markdown_doc, encoding="utf-8")


def _language_matrix_rows(matrix: pd.DataFrame, *, value_type: str) -> list[list[str]]:
    rows = []
    for language, row in matrix.iterrows():
        formatter = _fmt_pct if value_type == "rate" else _fmt_ms
        rows.append([str(language), *[formatter(row[model]) for model in matrix.columns]])
    return rows


def _matrix_values(matrix: pd.DataFrame) -> dict[str, dict[str, float | None]]:
    values: dict[str, dict[str, float | None]] = {}
    for language, row in matrix.iterrows():
        values[str(language)] = {str(model): _json_number(row[model]) for model in matrix.columns}
    return values


def _json_number(value: Any) -> float | None:
    try:
        float_value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(float_value):
        return None
    return float_value


def _load_model_metrics(
    span_set_dir: Path,
    *,
    min_hold_span_duration: float,
    max_hold_span_duration: float,
) -> list[ModelMetrics]:
    discovered: list[tuple[Path, Path, Path, Path]] = []
    for child in sorted(span_set_dir.iterdir()):
        if not child.is_dir() or child.name == "comparison":
            continue
        for metrics_dir in (child / "metrics", child):
            tradeoff_path = metrics_dir / "tradeoff.parquet"
            summary_path = metrics_dir / "summary.json"
            if tradeoff_path.exists() and summary_path.exists():
                discovered.append((child, metrics_dir, tradeoff_path, summary_path))
                break

    if not discovered:
        raise FileNotFoundError(
            f"No model metric artifacts found under {span_set_dir}; expected */metrics/tradeoff.parquet "
            "and */metrics/summary.json.",
        )

    base_names = []
    manifests: dict[Path, dict[str, Any]] = {}
    for run_dir, _, _, _ in discovered:
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        manifests[run_dir] = manifest
        base_names.append(_display_name_from_manifest(manifest) or _adapter_name_from_run_dir(run_dir))
    duplicate_names = {name for name in base_names if base_names.count(name) > 1}
    models = []
    for run_dir, metrics_dir, tradeoff_path, summary_path in discovered:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        _validate_summary_durations(
            summary,
            summary_path=summary_path,
            min_hold_span_duration=min_hold_span_duration,
            max_hold_span_duration=max_hold_span_duration,
        )

        manifest = manifests[run_dir]
        tradeoff = pd.read_parquet(tradeoff_path)
        _validate_tradeoff(tradeoff, tradeoff_path=tradeoff_path)

        base_name = _display_name_from_manifest(manifest) or _adapter_name_from_run_dir(run_dir)
        name = f"{base_name} ({run_dir.name})" if base_name in duplicate_names else base_name
        models.append(
            ModelMetrics(
                name=name,
                run_dir=run_dir,
                metrics_dir=metrics_dir,
                manifest=manifest,
                summary=summary,
                tradeoff=tradeoff,
            ),
        )
    return models


def _validate_summary_durations(
    summary: dict[str, Any],
    *,
    summary_path: Path,
    min_hold_span_duration: float,
    max_hold_span_duration: float,
) -> None:
    required = ("min_hold_span_duration", "max_hold_span_duration")
    missing = [key for key in required if key not in summary]
    if missing:
        raise ValueError(f"{summary_path} is missing required summary keys: {missing}")
    observed_min = float(summary["min_hold_span_duration"])
    observed_max = float(summary["max_hold_span_duration"])
    if not math.isclose(observed_min, float(min_hold_span_duration), abs_tol=EPS):
        raise ValueError(
            f"{summary_path} was computed with min_hold_span_duration={observed_min}, "
            f"expected {min_hold_span_duration}.",
        )
    if not math.isclose(observed_max, float(max_hold_span_duration), abs_tol=EPS):
        raise ValueError(
            f"{summary_path} was computed with max_hold_span_duration={observed_max}, "
            f"expected {max_hold_span_duration}.",
        )


def _validate_tradeoff(tradeoff: pd.DataFrame, *, tradeoff_path: Path) -> None:
    required = {
        "policy_type",
        "threshold",
        "action_delay",
        "timeout",
        "cutoff_rate",
        "mean_latency",
        "detect_rate",
    }
    missing = required - set(tradeoff.columns)
    if missing:
        raise ValueError(f"{tradeoff_path} is missing required columns: {sorted(missing)}")
    if tradeoff.empty:
        raise ValueError(f"{tradeoff_path} is empty")


def _combined_tradeoff(models: list[ModelMetrics]) -> pd.DataFrame:
    parts = []
    for model in models:
        df = model.tradeoff.copy()
        df["model"] = model.name
        parts.append(df)
    combined = pd.concat(parts, ignore_index=True)
    if combined[combined["policy_type"] == "model"].empty:
        raise ValueError("No model policy rows found in loaded tradeoff artifacts.")
    return combined


def _order_models_by_latency_at_cutoff(
    models: list[ModelMetrics],
    cutoff_budget_ops: pd.DataFrame,
    *,
    cutoff_budget: float,
) -> list[ModelMetrics]:
    sub = cutoff_budget_ops[
        (cutoff_budget_ops["budget_column"] == "cutoff_rate")
        & (cutoff_budget_ops["budget_value"].round(6) == round(float(cutoff_budget), 6))
    ].copy()
    latencies = sub.set_index("model")["value"].to_dict() if not sub.empty else {}

    def sort_key(model: ModelMetrics) -> tuple[bool, float, str]:
        latency = _finite_float(latencies.get(model.name))
        return (latency is None, math.inf if latency is None else latency, model.name)

    return sorted(models, key=sort_key)


def _vad_timeout_baseline(combined_tradeoff: pd.DataFrame) -> pd.DataFrame:
    if "policy_type" not in combined_tradeoff.columns:
        return pd.DataFrame(columns=["mean_latency", "cutoff_rate"])
    vad = combined_tradeoff[combined_tradeoff["policy_type"] == "vad"].copy()
    if vad.empty:
        return pd.DataFrame(columns=["mean_latency", "cutoff_rate"])
    columns = [
        column
        for column in ("mean_latency", "cutoff_rate", "n_hold_spans", "n_eot_spans")
        if column in vad.columns
    ]
    vad = vad[columns].dropna(subset=["mean_latency", "cutoff_rate"]).drop_duplicates()
    return vad.sort_values(["mean_latency", "cutoff_rate"], kind="stable").reset_index(drop=True)


def _fine_vad_baseline_from_span_set(
    span_set_dir: Path,
    *,
    min_hold_span_duration: float,
    max_hold_span_duration: float,
    fallback: pd.DataFrame,
) -> pd.DataFrame:
    span_set_path = span_set_dir / "span_set.parquet"
    if not span_set_path.exists():
        return fallback

    spans = pd.read_parquet(span_set_path)
    required = {"label", "duration"}
    if missing := required - set(spans.columns):
        raise ValueError(f"{span_set_path} is missing required columns: {sorted(missing)}")

    hold_durations = pd.to_numeric(
        spans.loc[spans["label"] == "hold", "duration"],
        errors="coerce",
    ).dropna()
    hold_durations = hold_durations[
        (hold_durations >= float(min_hold_span_duration) - EPS)
        & (hold_durations <= float(max_hold_span_duration) + EPS)
    ].to_numpy(dtype=float)
    if hold_durations.size == 0:
        return fallback

    fallback_max_delay = _finite_float(fallback["mean_latency"].max()) if "mean_latency" in fallback.columns else None
    max_delay = max(float(max_hold_span_duration), fallback_max_delay or 0.0)
    delay_grid = np.round(
        np.arange(
            float(min_hold_span_duration),
            max_delay + VAD_BASELINE_TABLE_STEP / 2.0,
            VAD_BASELINE_TABLE_STEP,
        ),
        6,
    )
    delay_grid = np.unique(np.concatenate([delay_grid, np.asarray(LATENCY_BUDGET_COMPARISON, dtype=float)]))
    delay_grid = delay_grid[(delay_grid >= float(min_hold_span_duration) - EPS) & (delay_grid <= max_delay + EPS)]

    return pd.DataFrame(
        [
            {
                "mean_latency": float(delay),
                "cutoff_rate": float((hold_durations > float(delay) + EPS).mean()),
            }
            for delay in delay_grid
        ],
    ).sort_values(["mean_latency", "cutoff_rate"], kind="stable").reset_index(drop=True)


def _make_plots(
    *,
    output_dir: Path,
    models: list[ModelMetrics],
    model_order: list[str],
    colors: dict[str, str],
    pareto: pd.DataFrame,
    vad_timeout_baseline: pd.DataFrame,
    latency_budget_ops: pd.DataFrame,
    cutoff_budget_ops: pd.DataFrame,
) -> list[str]:
    images: list[str] = []
    plt.style.use("seaborn-v0_8-darkgrid")

    fig, ax = plt.subplots(figsize=(8.0, 5.4), constrained_layout=True)
    for model in model_order:
        front = pareto[pareto["model"] == model].sort_values("mean_latency", kind="stable")
        ax.plot(
            front["mean_latency"],
            front["cutoff_rate"],
            color=colors[model],
            linewidth=1.0,
            alpha=1.0,
            label=model,
        )
    if not vad_timeout_baseline.empty:
        ax.plot(
            vad_timeout_baseline["mean_latency"],
            vad_timeout_baseline["cutoff_rate"],
            color="#4d4d4d",
            linestyle="--",
            linewidth=1.0,
            alpha=1.0,
            label="VAD baseline",
            zorder=1,
        )
    ax.set_xlabel("Mean latency on true EoT (s)")
    ax.set_ylabel("False cutoff rate on pause spans")
    _set_dynamic_policy_limits(ax, pareto)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(0.2))
    ax.xaxis.set_minor_locator(ticker.MultipleLocator(0.1))
    ax.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1.0))
    ax.legend(frameon=False, loc="best")
    images.append(_save_fig(fig, output_dir / "pareto_frontier.png"))

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), constrained_layout=True)
    for ax, budget in zip(np.atleast_1d(axes), LATENCY_BUDGET_COMPARISON, strict=True):
        _plot_single_budget_operating_point(
            latency_budget_ops,
            model_order=model_order,
            colors=colors,
            ax=ax,
            budget_value=float(budget),
            title=f"Latency budget {budget:.1f}s",
            ylabel="Best false-cutoff rate (%)",
            value_scale=100.0,
        )
    latency_budget_plot = _save_fig(fig, output_dir / "cutoff_rate_at_latency_budget_300_600ms.png")

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), constrained_layout=True)
    for ax, budget in zip(np.atleast_1d(axes), CUTOFF_BUDGET_COMPARISON, strict=True):
        _plot_single_budget_operating_point(
            cutoff_budget_ops,
            model_order=model_order,
            colors=colors,
            ax=ax,
            budget_value=float(budget),
            title=f"Cutoff budget {int(round(budget * 100))}%",
            ylabel="Best mean latency (ms)",
            value_scale=1000.0,
        )
    cutoff_budget_plot = _save_fig(fig, output_dir / "latency_at_cutoff_budget_5_10pct.png")
    images.extend([latency_budget_plot, cutoff_budget_plot])
    return images


def _plot_single_budget_operating_point(
    odf: pd.DataFrame,
    *,
    model_order: list[str],
    colors: dict[str, str],
    ax,
    budget_value: float,
    title: str,
    ylabel: str,
    value_scale: float,
) -> None:
    sub = odf[odf["budget_value"].round(6) == round(float(budget_value), 6)]
    sub = sub.set_index("model").reindex(model_order)
    vals = sub["value"].to_numpy(dtype=float) * value_scale
    x = np.arange(len(model_order))
    ax.bar(x, vals, width=0.65, color=[colors[model] for model in model_order])
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(model_order, rotation=20, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_axisbelow(True)


def _vad_cutoff_at_latency_budget(vad_timeout_baseline: pd.DataFrame, latency_budget: float) -> float | None:
    point = _best_vad_operating_point(
        vad_timeout_baseline,
        budget_column="mean_latency",
        budget_value=latency_budget,
        optimize_column="cutoff_rate",
    )
    return None if point is None else _finite_float(point.get("cutoff_rate"))


def _vad_latency_at_cutoff_budget(vad_timeout_baseline: pd.DataFrame, cutoff_budget: float) -> float | None:
    point = _best_vad_operating_point(
        vad_timeout_baseline,
        budget_column="cutoff_rate",
        budget_value=cutoff_budget,
        optimize_column="mean_latency",
    )
    return None if point is None else _finite_float(point.get("mean_latency"))


def _best_vad_operating_point(
    vad_timeout_baseline: pd.DataFrame,
    *,
    budget_column: str,
    budget_value: float,
    optimize_column: str,
) -> dict[str, Any] | None:
    if vad_timeout_baseline.empty:
        return None
    required = {budget_column, optimize_column}
    if missing := required - set(vad_timeout_baseline.columns):
        raise ValueError(f"VAD baseline is missing required columns: {sorted(missing)}")

    feasible = vad_timeout_baseline[
        pd.to_numeric(vad_timeout_baseline[budget_column], errors="coerce") <= float(budget_value) + EPS
    ].copy()
    if feasible.empty:
        return None
    best = feasible.sort_values([optimize_column, budget_column], kind="stable").iloc[0]
    return best.to_dict()


MetricCell = tuple[str, bool]


def _latency_budget_metric_headers() -> list[str]:
    return [
        "Model",
        *[
            f"Best cutoff rate @ {_format_latency_budget_header(budget)} latency"
            for budget in LATENCY_BUDGET_COMPARISON
        ],
    ]


def _cutoff_budget_metric_headers() -> list[str]:
    return [
        "Model",
        *[
            f"Best mean latency @ {_format_cutoff_budget_header(budget)} cutoff"
            for budget in CUTOFF_BUDGET_COMPARISON
        ],
    ]


def _latency_budget_metric_rows(
    latency_budget_ops: pd.DataFrame,
    *,
    model_order: list[str],
    vad_table_baseline: pd.DataFrame,
) -> list[list[MetricCell]]:
    values = _metric_values_from_operating_points(
        latency_budget_ops,
        budget_column="mean_latency",
        budget_values=LATENCY_BUDGET_COMPARISON,
    )
    values["VAD baseline"] = [
        _vad_cutoff_at_latency_budget(vad_table_baseline, budget)
        for budget in LATENCY_BUDGET_COMPARISON
    ]
    return _metric_rows(
        [*model_order, "VAD baseline"],
        values,
        formatter=_fmt_pct,
    )


def _cutoff_budget_metric_rows(
    cutoff_budget_ops: pd.DataFrame,
    *,
    model_order: list[str],
    vad_table_baseline: pd.DataFrame,
) -> list[list[MetricCell]]:
    values = _metric_values_from_operating_points(
        cutoff_budget_ops,
        budget_column="cutoff_rate",
        budget_values=CUTOFF_BUDGET_COMPARISON,
    )
    values["VAD baseline"] = [
        _vad_latency_at_cutoff_budget(vad_table_baseline, budget)
        for budget in CUTOFF_BUDGET_COMPARISON
    ]
    return _metric_rows(
        [*model_order, "VAD baseline"],
        values,
        formatter=_fmt_ms,
    )


def _metric_values_from_operating_points(
    operating_points: pd.DataFrame,
    *,
    budget_column: str,
    budget_values: tuple[float, ...],
) -> dict[str, list[float | None]]:
    rows = operating_points[operating_points["budget_column"] == budget_column].copy()
    out: dict[str, list[float | None]] = {}
    for model, model_rows in rows.groupby("model", sort=False):
        model_values = []
        for budget in budget_values:
            match = model_rows[model_rows["budget_value"].round(6) == round(float(budget), 6)]
            value = None if match.empty else _finite_float(match.iloc[0].get("value"))
            model_values.append(value)
        out[str(model)] = model_values
    return out


def _metric_rows(
    model_order: list[str],
    values_by_model: dict[str, list[float | None]],
    *,
    formatter,
) -> list[list[MetricCell]]:
    width = max((len(values) for values in values_by_model.values()), default=0)
    best_values: list[float | None] = []
    for column_index in range(width):
        finite_values = [
            values[column_index]
            for values in values_by_model.values()
            if column_index < len(values) and values[column_index] is not None
        ]
        best_values.append(min(finite_values) if finite_values else None)

    rows: list[list[MetricCell]] = []
    for model in model_order:
        values = values_by_model.get(model, [None] * width)
        row: list[MetricCell] = [(model, False)]
        for column_index in range(width):
            value = values[column_index] if column_index < len(values) else None
            best_value = best_values[column_index]
            is_best = (
                value is not None
                and best_value is not None
                and math.isclose(float(value), float(best_value), abs_tol=EPS)
            )
            row.append((formatter(value), is_best))
        rows.append(row)
    return rows


def _markdown_metric_table(headers: list[str], rows: list[list[MetricCell]]) -> str:
    header = "| " + " | ".join(_escape_markdown_cell(value) for value in headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join(
        "| "
        + " | ".join(
            f"**{_escape_markdown_cell(value)}**" if is_best else _escape_markdown_cell(value)
            for value, is_best in row
        )
        + " |"
        for row in rows
    )
    return "\n".join(part for part in (header, divider, body) if part)


def _format_latency_budget_header(budget: float) -> str:
    return f"{float(budget):.1f}s"


def _format_cutoff_budget_header(budget: float) -> str:
    return f"{int(round(float(budget) * 100.0))}%"


def _set_dynamic_policy_limits(ax, pareto: pd.DataFrame) -> None:
    del pareto
    ax.set_xlim(0.0, 1.5)
    ax.set_ylim(0.0, 0.5)
    ax.yaxis.set_major_locator(ticker.MultipleLocator(0.1))
    ax.yaxis.set_minor_locator(ticker.MultipleLocator(0.05))


def _save_fig(fig: plt.Figure, path: Path) -> str:
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path.name


def _remove_stale_report_artifacts(output_dir: Path) -> None:
    (output_dir / "report.html").unlink(missing_ok=True)
    for filename in STALE_REPORT_PLOTS:
        (output_dir / filename).unlink(missing_ok=True)
    for pattern in REPORT_DATA_ARTIFACT_PATTERNS:
        for path in output_dir.glob(pattern):
            path.unlink()


def _ensure_report_images(images: list[str]) -> None:
    image_set = set(images)
    for required_image in REPORT_PLOTS:
        if required_image not in image_set:
            raise ValueError(f"comparison report is missing required plot: {required_image}")


def _write_markdown(
    *,
    output_dir: Path,
    model_order: list[str],
    latency_budget_ops: pd.DataFrame,
    cutoff_budget_ops: pd.DataFrame,
    vad_table_baseline: pd.DataFrame,
    images: list[str],
) -> None:
    _ensure_report_images(images)
    markdown_doc = f"""# EoT Model Comparison

## Pareto Frontier

![Pareto frontier](pareto_frontier.png)

## Best Cutoff Rate at Latency Budget

![Best cutoff rate at latency budgets](cutoff_rate_at_latency_budget_300_600ms.png)

{_markdown_metric_table(_latency_budget_metric_headers(), _latency_budget_metric_rows(latency_budget_ops, model_order=model_order, vad_table_baseline=vad_table_baseline))}

## Best Latency at Cutoff Budget

![Best latency at cutoff budgets](latency_at_cutoff_budget_5_10pct.png)

{_markdown_metric_table(_cutoff_budget_metric_headers(), _cutoff_budget_metric_rows(cutoff_budget_ops, model_order=model_order, vad_table_baseline=vad_table_baseline))}

## Operating Points

{_markdown_table(_ops_headers(), _combined_ops_rows(cutoff_budget_ops, latency_budget_ops, model_order=model_order))}
"""
    (output_dir / "report.md").write_text(markdown_doc, encoding="utf-8")


def _combined_ops_rows(
    cutoff_budget_ops: pd.DataFrame,
    latency_budget_ops: pd.DataFrame,
    *,
    model_order: list[str],
) -> list[list[str]]:
    rows: list[list[str]] = []
    for label, budget_column, odf in (
        ("Cutoff", "cutoff_rate", cutoff_budget_ops),
        ("Latency", "mean_latency", latency_budget_ops),
    ):
        rows.extend(_ops_rows(label, budget_column, odf, model_order=model_order))
    return rows


def _ops_headers() -> list[str]:
    return ["Type", "Budget", "Model", "Mean Latency", "Cutoff", "Detect", "Threshold", "Action Delay", "Timeout"]


def _ops_rows(label: str, budget_column: str, odf: pd.DataFrame, *, model_order: list[str]) -> list[list[str]]:
    order = {model: idx for idx, model in enumerate(model_order)}
    sub = odf[odf["budget_column"] == budget_column].copy()
    sub["model_order"] = sub["model"].map(order)
    sub = sub.sort_values(["budget_value", "model_order"], kind="stable")

    rows = []
    for _, row in sub.iterrows():
        budget = (
            _fmt_pct(row["budget_value"])
            if budget_column == "cutoff_rate"
            else f"{int(round(float(row['budget_value']) * 1000))}ms"
        )
        rows.append(
            [
                label,
                budget,
                str(row["model"]),
                _fmt(row.get("mean_latency")),
                _fmt_pct(row.get("cutoff_rate")),
                _fmt_pct(row.get("detect_rate")),
                _fmt(row.get("threshold")),
                _fmt(row.get("action_delay")),
                _fmt(row.get("timeout")),
            ],
        )
    return rows


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header = "| " + " | ".join(_escape_markdown_cell(value) for value in headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join(
        "| " + " | ".join(_escape_markdown_cell(value) for value in row) + " |"
        for row in rows
    )
    return "\n".join(part for part in (header, divider, body) if part)


def _escape_markdown_cell(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _adapter_name_from_run_dir(run_dir: Path) -> str:
    return run_dir.name.split("__", 1)[0]


def _display_name_from_manifest(manifest: dict[str, Any]) -> str | None:
    value = manifest.get("display_name")
    if value is None and isinstance(manifest.get("model"), dict):
        value = manifest["model"].get("display_name")
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _model_colors(model_order: list[str]) -> dict[str, str]:
    cmap = plt.get_cmap("tab20")
    return {model: cmap(index % cmap.N) for index, model in enumerate(model_order)}


def _finite_float(value: Any) -> float | None:
    try:
        float_value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(float_value):
        return None
    return float_value


def _fmt(value: Any) -> str:
    try:
        float_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(float_value):
        return "-"
    return f"{float_value:.3f}"


def _fmt_ms(value: Any) -> str:
    float_value = _finite_float(value)
    if float_value is None:
        return "-"
    return f"{float_value * 1000.0:.0f} ms"


def _fmt_pct(value: Any) -> str:
    try:
        float_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(float_value):
        return "-"
    return f"{100.0 * float_value:.1f}%"
