from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from . import __version__
from .adapters import load_adapter, load_streaming_adapter
from .io import (
    DEFAULT_INFERENCE_INTERVAL,
    DEFAULT_MIN_SILENCE,
    DEFAULT_TRANSCRIPT_LAG,
    build_span_set,
    iter_batches,
    load_hf_dataset,
)
from .languages import adapter_supports_language, row_language

DOTENV_PATH = Path(__file__).with_name(".env")
load_dotenv(DOTENV_PATH, override=False)
DEFAULT_PROGRESS_INTERVAL = 30.0
_EPS = 1e-6


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eot-harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    predict = subparsers.add_parser("predict", help="Run a model adapter and write predictions.parquet")
    predict.add_argument("--path", "--repo-id", dest="path", required=True, help="Hugging Face dataset path")
    predict.add_argument("--name", "--subset", dest="name", required=True, help="Hugging Face dataset config name")
    predict.add_argument("--split", default="validation", help="Dataset split")
    predict.add_argument("--revision", help="Optional Hugging Face dataset revision")
    predict.add_argument("--adapter", required=True, help="Adapter import path")
    predict.add_argument("--output-dir", default="output", help="Root directory for span-set and model artifacts")
    predict.add_argument(
        "--min-silence-span",
        type=float,
        default=DEFAULT_MIN_SILENCE,
        help="Minimum silence span duration to include in the prediction span set",
    )
    predict.add_argument("--batch-size", type=int, default=128)
    predict.add_argument("--inference-interval", type=float, default=DEFAULT_INFERENCE_INTERVAL)
    predict.add_argument("--transcript-lag", type=float, default=DEFAULT_TRANSCRIPT_LAG)
    predict.add_argument("--overwrite", action="store_true", help="Overwrite an existing model run directory")
    predict.add_argument(
        "--progress-interval",
        type=float,
        default=DEFAULT_PROGRESS_INTERVAL,
        help="Seconds between progress logs. Set to 0 to disable progress logging.",
    )

    predict_streaming = subparsers.add_parser(
        "predict-streaming",
        help="Run a streaming/API adapter and write predictions.parquet",
    )
    predict_streaming.add_argument("--path", "--repo-id", dest="path", required=True, help="Hugging Face dataset path")
    predict_streaming.add_argument("--name", "--subset", dest="name", required=True, help="Hugging Face dataset config name")
    predict_streaming.add_argument("--split", default="validation", help="Dataset split")
    predict_streaming.add_argument("--revision", help="Optional Hugging Face dataset revision")
    predict_streaming.add_argument("--adapter", required=True, help="Streaming adapter import path")
    predict_streaming.add_argument("--output-dir", required=True, help="Root directory for span-set and model artifacts")
    predict_streaming.add_argument("--inference-interval", type=float, default=DEFAULT_INFERENCE_INTERVAL)
    predict_streaming.add_argument("--concurrency", type=int)
    predict_streaming.add_argument("--model", help="Optional adapter model override")
    predict_streaming.add_argument("--chunk-ms", type=int, help="Optional streaming chunk size override")
    predict_streaming.add_argument("--eot-threshold", type=float, help="Optional EoT threshold override (Deepgram Flux, Gradium)")
    predict_streaming.add_argument("--limit", type=int, help="Only score the first N dataset rows.")
    predict_streaming.add_argument("--overwrite", action="store_true", help="Overwrite existing model run directories")
    predict_streaming.add_argument(
        "--progress-interval",
        type=float,
        default=DEFAULT_PROGRESS_INTERVAL,
        help="Seconds between progress logs. Set to 0 to disable progress logging.",
    )
    predict_streaming.add_argument(
        "--skip-unsupported-languages",
        action="store_true",
        help="Skip rows whose language is unsupported by the streaming adapter.",
    )
    predict_streaming.add_argument(
        "--skip-errors",
        action="store_true",
        help="Skip rows whose streaming API call fails instead of aborting the full run.",
    )

    metrics = subparsers.add_parser("compute-metrics", help="Compute metrics from predictions.parquet")
    metrics.add_argument("--predictions", required=True, help="Path to predictions.parquet")
    metrics.add_argument("--output-dir", required=True, help="Directory for computed metrics")
    metrics.add_argument(
        "--score-point",
        type=float,
        help=(
            "Silence duration where the model score is sampled. Defaults to the prediction "
            "manifest score_point when present; otherwise metrics use the max score in each span."
        ),
    )
    metrics.add_argument(
        "--min-hold-span-duration",
        type=float,
        default=0.2,
        help="Exclude pause/hold spans shorter than this duration from eval.",
    )
    metrics.add_argument(
        "--max-hold-span-duration",
        type=float,
        default=5.0,
        help="Exclude pause/hold spans longer than this duration from eval.",
    )

    compare = subparsers.add_parser("compare-models", help="Build a model comparison report for a span-set directory")
    compare.add_argument("span_set_dir", help="Span-set directory containing per-model metric artifacts")
    compare.add_argument(
        "--min-hold-span-duration",
        type=float,
        default=0.2,
        help="Required min hold span duration used by the loaded metric artifacts.",
    )
    compare.add_argument(
        "--max-hold-span-duration",
        type=float,
        default=5.0,
        help="Required max hold span duration used by the loaded metric artifacts.",
    )

    compare_languages = subparsers.add_parser(
        "compare-languages",
        help="Build language/model AUC and AP heatmaps for a span-set root directory",
    )
    compare_languages.add_argument("span_set_root", help="Span-set root containing per-language span-set directories")
    compare_languages.add_argument(
        "--output-dir",
        help="Directory for the language comparison artifacts. Defaults to <span-set-root>/language_comparison.",
    )
    compare_languages.add_argument(
        "--min-hold-span-duration",
        type=float,
        default=0.2,
        help="Required min hold span duration used by the loaded metric artifacts.",
    )
    compare_languages.add_argument(
        "--max-hold-span-duration",
        type=float,
        default=5.0,
        help="Required max hold span duration used by the loaded metric artifacts.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "predict":
        _run_predict(args)
        return

    if args.command == "predict-streaming":
        _run_predict_streaming(args)
        return

    if args.command == "compute-metrics":
        _run_compute_metrics(args)
        return

    if args.command == "compare-models":
        _run_compare_models(args)
        return

    if args.command == "compare-languages":
        _run_compare_languages(args)
        return

    raise RuntimeError(f"Unhandled command: {args.command}")


def _load_dataset_config(args) -> dict[str, Any]:
    config = {
        "path": _dataset_path(args),
        "name": _dataset_name(args),
        "split": _dataset_split(args),
    }
    revision = _dataset_revision(args)
    if revision is not None:
        config["revision"] = revision
    return config


def _span_set_config(args, min_silence_span: float, *, language: str | None = None) -> dict[str, Any]:
    config = {
        "path": _dataset_path(args),
        "split": _dataset_split(args),
        "min_silence_span": float(min_silence_span),
    }
    revision = _dataset_revision(args)
    if revision is not None:
        config["revision"] = revision
    if language is not None:
        config["language"] = str(language)
    return config


def _dataset_path(args) -> str:
    value = getattr(args, "path", None) or getattr(args, "repo_id", None)
    if value is None or not str(value).strip():
        raise ValueError("Dataset path is required.")
    return str(value)


def _dataset_name(args) -> str:
    value = getattr(args, "name", None) or getattr(args, "subset", None)
    if value is None or not str(value).strip():
        raise ValueError("Dataset name is required.")
    return str(value)


def _dataset_split(args) -> str:
    value = getattr(args, "split", None)
    if value is None or not str(value).strip():
        raise ValueError("Dataset split is required.")
    return str(value)


def _dataset_revision(args) -> str | None:
    value = getattr(args, "revision", None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _progress_interval(args) -> float | None:
    value = float(getattr(args, "progress_interval", DEFAULT_PROGRESS_INTERVAL))
    if value < 0:
        raise ValueError("progress_interval must be non-negative")
    if value == 0:
        return None
    return value


class _ProgressReporter:
    def __init__(self, *, label: str, total: int, unit: str, interval: float | None) -> None:
        self.label = label
        self.total = int(total)
        self.unit = unit
        self.interval = interval
        self.completed = 0
        self.started = time.perf_counter()
        self.next_log = self.started + float(interval or 0)
        self.enabled = interval is not None

    def start(self, detail: str = "") -> None:
        if not self.enabled:
            return
        suffix = f"; {detail}" if detail else ""
        _log_progress(f"{self.label} start: {self.total} {self.unit}{suffix}")

    def advance(self, count: int = 1) -> None:
        if count <= 0:
            return
        self.completed += int(count)
        if not self.enabled:
            return

        now = time.perf_counter()
        if self.completed < self.total and now < self.next_log:
            return
        self._emit(now, "progress")
        while now >= self.next_log:
            self.next_log += float(self.interval or 0)

    def finish(self, detail: str = "") -> None:
        if not self.enabled:
            return
        self._emit(time.perf_counter(), "done", detail=detail)

    def _emit(self, now: float, status: str, *, detail: str = "") -> None:
        elapsed = max(0.0, now - self.started)
        rate = self.completed / elapsed if elapsed > 0 else 0.0
        if self.total > 0:
            pct = min(100.0, 100.0 * self.completed / self.total)
            count_text = f"{self.completed}/{self.total} {self.unit} ({pct:.1f}%)"
        else:
            count_text = f"{self.completed} {self.unit}"

        parts = [
            f"{self.label} {status}: {count_text}",
            f"elapsed {_format_duration(elapsed)}",
        ]
        if rate > 0:
            parts.append(f"rate {rate:.2f} {self.unit}/s")
        if status == "progress" and rate > 0 and self.total > self.completed:
            parts.append(f"eta {_format_duration((self.total - self.completed) / rate)}")
        if detail:
            parts.append(detail)
        _log_progress("; ".join(parts))


def _log_progress(message: str) -> None:
    print(f"[eot-harness] {message}", file=sys.stderr, flush=True)


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _format_language_list(languages: list[str]) -> str:
    values = sorted(str(language) for language in languages)
    if len(values) <= 8:
        return ", ".join(values) or "-"
    return f"{len(values)} languages ({', '.join(values[:8])}, ...)"


def _format_skip_summary(skipped_languages: dict[str, str]) -> str:
    if not skipped_languages:
        return "none"
    counts: dict[str, int] = defaultdict(int)
    for reason in skipped_languages.values():
        counts[str(reason)] += 1
    return ", ".join(f"{reason}={count}" for reason, count in sorted(counts.items()))


def _prediction_point_count(span_rows: list[dict[str, Any]], inference_interval: float) -> int:
    interval = float(inference_interval)
    if interval <= 0:
        raise ValueError("inference_interval must be positive")
    total = 0
    for span in span_rows:
        start = float(span["start"])
        end = float(span["end"])
        n_steps = max(0, int(math.floor((end - start) / interval + _EPS)))
        count = n_steps + 1
        last = start + n_steps * interval
        if last < end - _EPS:
            count += 1
        total += count
    return total


def _model_config(args, adapter) -> dict[str, Any]:
    config = {
        "adapter": str(args.adapter),
        "adapter_id": str(adapter.adapter_id),
        "inference_interval": float(args.inference_interval),
        "transcript_lag": float(args.transcript_lag),
    }
    display_name = _adapter_display_name(adapter)
    if display_name is not None:
        config["display_name"] = display_name
    max_audio_sec = _adapter_max_audio_sec(adapter)
    if max_audio_sec is not None:
        config["max_audio_sec"] = max_audio_sec
    return config


def _adapter_score_point(adapter) -> float | None:
    score_point = getattr(adapter, "score_point", None)
    if score_point is None:
        return None
    value = float(score_point)
    if value < 0:
        raise ValueError(f"Adapter {adapter.adapter_id!r} has invalid score_point={score_point!r}.")
    return value


def _adapter_display_name(adapter) -> str | None:
    display_name = getattr(adapter, "display_name", None)
    if display_name is None:
        return None
    display_name = str(display_name).strip()
    if not display_name:
        raise ValueError(f"Adapter {adapter.adapter_id!r} has an empty display_name.")
    return display_name


def _adapter_max_audio_sec(adapter) -> float | None:
    max_audio_sec = getattr(adapter, "max_audio_sec", None)
    if max_audio_sec is None:
        return None
    value = float(max_audio_sec)
    if value <= 0:
        raise ValueError(f"Adapter {adapter.adapter_id!r} has invalid max_audio_sec={max_audio_sec!r}.")
    return value


def _span_set_dir_name(config: dict[str, Any]) -> str:
    parts = [_slug_dataset_part(config["path"])]
    if config.get("revision") is not None:
        parts.append(f"revision_{_slug_dataset_part(config['revision'])}")
    parts.extend(
        [
            _slug_dataset_part(config["split"]),
            f"min_silence_{_format_seconds_slug(float(config['min_silence_span']))}",
        ],
    )
    return "__".join(parts)


def _model_run_dir_name(adapter_ref: str, model_config: dict[str, Any]) -> str:
    return f"{_adapter_name_slug(adapter_ref)}__{_config_hash(model_config)}"


def _streaming_model_run_dir_name(adapter_ref: str, adapter) -> str:
    return f"{_streaming_adapter_name_slug(adapter_ref, adapter)}__{_streaming_model_suffix(adapter)}"


def _streaming_adapter_name_slug(adapter_ref: str, adapter) -> str:
    class_name = adapter.__class__.__name__
    legacy_names = {
        "AssemblyAIStreamingAdapter": "assemblyai_streaming_adapter",
        "OpenAIRealtime2Adapter": "openai_realtime2_adapter",
    }
    if class_name in legacy_names:
        return legacy_names[class_name]
    return _adapter_name_slug(adapter_ref)


def _streaming_model_suffix(adapter) -> str:
    class_name = adapter.__class__.__name__
    if class_name == "OpenAIRealtime2Adapter":
        return _streaming_suffix_slug(f"{adapter.model}_semantic_vad_{adapter.eagerness}")

    adapter_id = str(adapter.adapter_id)
    suffix = adapter_id.rsplit("/", 1)[-1]
    return _streaming_suffix_slug(suffix)


def _streaming_suffix_slug(value: str) -> str:
    return _slug_dataset_part(value).replace("-", "_")


def _streaming_prediction_config(adapter, args) -> dict[str, Any]:
    config = {
        "adapter_id": str(adapter.adapter_id),
        "streaming": True,
        "inference_interval": float(args.inference_interval),
    }
    for attr in (
        "model",
        "chunk_ms",
        "eot_threshold",
        "min_turn_silence",
        "max_turn_silence",
        "end_of_turn_confidence_threshold",
        "max_endpoint_delay_ms",
        "endpointing_ms",
        "max_delay",
        "end_of_utterance_silence_trigger",
        "eagerness",
        "post_audio_wait_s",
        "url",
    ):
        if hasattr(adapter, attr):
            config[attr] = getattr(adapter, attr)
    return config


def _write_or_validate_span_set(
    span_set_dir: Path,
    span_config: dict[str, Any],
    span_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest_path = span_set_dir / "span_set_manifest.json"
    span_set_path = span_set_dir / "span_set.parquet"
    manifest = {
        "harness_version": __version__,
        "span_set_id": _config_hash({"span_set": span_config}, length=12),
        "dataset": span_config,
        "n_spans": len(span_rows),
    }

    if manifest_path.exists():
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing_manifest.get("dataset") != span_config:
            raise ValueError(f"Existing span set manifest does not match requested dataset params: {manifest_path}")
        manifest = {**manifest, **existing_manifest}

    if span_set_path.exists():
        existing_rows = pd.read_parquet(span_set_path).to_dict("records")
        _validate_span_rows_match(existing_rows, span_rows, source=str(span_set_path))
    else:
        pd.DataFrame(span_rows).to_parquet(span_set_path, index=False)

    if not manifest_path.exists():
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return manifest


def _validate_prediction_span_set(prediction_rows: list[dict[str, Any]], span_rows: list[dict[str, Any]]) -> None:
    expected = _span_key_set(span_rows)
    observed = _span_key_set(prediction_rows)
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    if missing or extra:
        raise ValueError(
            "Prediction span set does not match dataset span set: "
            f"missing={missing[:5]} total_missing={len(missing)}, "
            f"extra={extra[:5]} total_extra={len(extra)}",
        )


def _validate_span_rows_match(
    existing_rows: list[dict[str, Any]],
    requested_rows: list[dict[str, Any]],
    *,
    source: str,
) -> None:
    existing = _span_key_set(existing_rows)
    requested = _span_key_set(requested_rows)
    missing = sorted(requested - existing)
    extra = sorted(existing - requested)
    if missing or extra:
        raise ValueError(
            f"Existing span set at {source} does not match requested dataset params: "
            f"missing={missing[:5]} total_missing={len(missing)}, "
            f"extra={extra[:5]} total_extra={len(extra)}",
        )


def _span_key_set(rows: list[dict[str, Any]]) -> set[tuple[str, int]]:
    return {(str(row["id"]), int(row["span_index"])) for row in rows}


def _config_hash(config: dict[str, Any], *, length: int = 10) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _slug_dataset_part(value: Any) -> str:
    text = str(value).strip().replace("/", "__")
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return text or "unknown"


def _adapter_name_slug(adapter_ref: str) -> str:
    name = adapter_ref.rsplit(":", 1)[-1].rsplit(".", 1)[-1]
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()
    return _slug_dataset_part(name)


def _format_seconds_slug(value: float) -> str:
    millis = round(value * 1000)
    if abs(value * 1000 - millis) < 1e-6:
        return f"{millis}ms"
    text = f"{value:.6f}".rstrip("0").rstrip(".").replace(".", "p")
    return f"{text}s"


def _group_rows_by_language(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        language = row_language(row)
        grouped[language].append(row)
    return dict(sorted(grouped.items()))


def _model_run_artifact_is_complete(
    output_dir: Path,
    *,
    span_config: dict[str, Any],
    load_config: dict[str, Any],
    model_run_id: str,
    model_manifest: dict[str, Any],
    span_rows: list[dict[str, Any]],
) -> bool:
    predictions_path = output_dir / "predictions.parquet"
    manifest_path = output_dir / "manifest.json"
    if not predictions_path.exists() or not manifest_path.exists():
        return False

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("dataset") != span_config:
            return False
        if manifest.get("load_dataset") != load_config:
            return False
        if manifest.get("model_run_id") != model_run_id:
            return False
        if manifest.get("model") != model_manifest:
            return False

        prediction_rows = pd.read_parquet(predictions_path).to_dict("records")
        _validate_prediction_span_set(prediction_rows, span_rows)
    except Exception:
        return False
    return True


def _streaming_model_run_artifact_can_be_reused(
    output_dir: Path,
    *,
    span_config: dict[str, Any],
    load_config: dict[str, Any],
    model_run_id: str,
    prediction_config: dict[str, Any],
    span_rows: list[dict[str, Any]],
) -> bool:
    predictions_path = output_dir / "predictions.parquet"
    manifest_path = output_dir / "manifest.json"
    if not predictions_path.exists() or not manifest_path.exists():
        return False

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("dataset") != span_config:
            return False
        if manifest.get("load_dataset") != load_config:
            return False
        if manifest.get("model_run_id") != model_run_id:
            return False
        for key, value in prediction_config.items():
            if manifest.get(key) != value:
                return False

        prediction_rows = pd.read_parquet(predictions_path).to_dict("records")
        if not prediction_rows:
            return False
        expected = _span_key_set(span_rows)
        observed = _span_key_set(prediction_rows)
        if not observed <= expected:
            return False
    except Exception:
        return False
    return True


def _run_predict(args) -> list[Path]:
    progress_interval = _progress_interval(args)
    token = os.getenv("HF_TOKEN")
    load_config = _load_dataset_config(args)
    if progress_interval is not None:
        revision = f" revision={load_config['revision']}" if load_config.get("revision") is not None else ""
        _log_progress(
            f"predict: loading dataset {load_config['path']}::{load_config['name']} "
            f"split={load_config['split']}{revision}",
        )
    ds = load_hf_dataset(
        load_config["path"],
        load_config["name"],
        load_config["split"],
        revision=load_config.get("revision"),
        token=token,
    )
    min_silence_span = float(getattr(args, "min_silence_span", DEFAULT_MIN_SILENCE))
    if min_silence_span <= 0:
        raise ValueError("min_silence_span must be positive")

    span_rows = build_span_set(ds, min_silence_span=min_silence_span)
    if not span_rows:
        raise ValueError("Dataset produced an empty prediction span set.")
    span_rows_by_language = _group_rows_by_language(span_rows)

    adapter = load_adapter(args.adapter)
    output_root = Path(getattr(args, "output_dir", "output")).expanduser().resolve()
    span_root_config = _span_set_config(args, min_silence_span)
    span_set_root = output_root / _span_set_dir_name(span_root_config)
    model_config = _model_config(args, adapter)
    model_run_id = _model_run_dir_name(args.adapter, model_config)
    model_manifest = dict(model_config)
    score_point = _adapter_score_point(adapter)
    if score_point is not None:
        model_manifest["score_point"] = score_point
    display_name = _adapter_display_name(adapter)
    output_dirs = {language: span_set_root / language / model_run_id for language in span_rows_by_language}

    span_set_manifests: dict[str, dict[str, Any]] = {}
    for language, language_span_rows in span_rows_by_language.items():
        span_set_dir = span_set_root / language
        span_set_dir.mkdir(parents=True, exist_ok=True)
        span_set_manifests[language] = _write_or_validate_span_set(
            span_set_dir,
            _span_set_config(args, min_silence_span, language=language),
            language_span_rows,
        )

    languages_to_run: list[str] = []
    skipped_languages: dict[str, str] = {}
    overwrite = bool(getattr(args, "overwrite", False))
    for language, output_dir in output_dirs.items():
        if not adapter_supports_language(adapter, language):
            skipped_languages[language] = "unsupported_language"
            continue
        span_config = _span_set_config(args, min_silence_span, language=language)
        if output_dir.exists() and not overwrite:
            if _model_run_artifact_is_complete(
                output_dir,
                span_config=span_config,
                load_config=load_config,
                model_run_id=model_run_id,
                model_manifest=model_manifest,
                span_rows=span_rows_by_language[language],
            ):
                skipped_languages[language] = "existing_predictions"
                continue
            raise FileExistsError(
                f"Model run directory already exists but is incomplete or stale: {output_dir}. "
                "Use --overwrite to replace it.",
            )
        languages_to_run.append(language)

    for language in languages_to_run:
        output_dirs[language].mkdir(parents=True, exist_ok=True)

    if not languages_to_run:
        if progress_interval is not None:
            _log_progress(f"predict: nothing to run; skipped languages: {_format_skip_summary(skipped_languages)}")
        return []

    prediction_rows_by_language: dict[str, list[dict[str, Any]]] = defaultdict(list)
    languages_to_run_set = set(languages_to_run)
    rows_to_predict = [row for row in ds if row_language(dict(row)) in languages_to_run_set]
    total_points = sum(
        _prediction_point_count(span_rows_by_language[language], float(args.inference_interval))
        for language in languages_to_run
    )
    progress = _ProgressReporter(
        label="predict",
        total=total_points,
        unit="prediction points",
        interval=progress_interval,
    )
    progress.start(
        "languages="
        f"{_format_language_list(languages_to_run)}; "
        f"skipped_languages={_format_skip_summary(skipped_languages)}; "
        f"batch_size={args.batch_size}",
    )
    for batch_meta, batch_inputs in iter_batches(
        rows_to_predict,
        batch_size=args.batch_size,
        inference_interval=args.inference_interval,
        transcript_lag=args.transcript_lag,
        min_silence_span=min_silence_span,
        max_audio_sec=_adapter_max_audio_sec(adapter),
    ):
        scores = adapter.predict_batch(batch_inputs)
        if len(scores) != len(batch_meta):
            raise ValueError(
                f"Adapter returned {len(scores)} scores for a batch of {len(batch_meta)} inputs.",
            )

        for meta, score in zip(batch_meta, scores, strict=True):
            language = str(meta["language"]).strip().lower()
            prediction_rows_by_language[language].append(
                {
                    "id": meta["id"],
                    "language": language,
                    "span_index": meta["span_index"],
                    "timestamp": meta["timestamp"],
                    "silence_dur": meta["silence_dur"],
                    "p_eot": float(score),
                    "label": meta["label"],
                },
            )
        progress.advance(len(batch_meta))

    run_dirs: list[Path] = []
    for language in languages_to_run:
        language_span_rows = span_rows_by_language[language]
        prediction_rows = prediction_rows_by_language.get(language, [])
        _validate_prediction_span_set(prediction_rows, language_span_rows)

        output_dir = output_dirs[language]
        predictions_path = output_dir / "predictions.parquet"
        manifest_path = output_dir / "manifest.json"
        span_config = _span_set_config(args, min_silence_span, language=language)
        span_set_manifest = span_set_manifests[language]

        pd.DataFrame(prediction_rows).to_parquet(predictions_path, index=False)
        manifest = {
            "harness_version": __version__,
            "span_set_id": span_set_manifest["span_set_id"],
            "model_run_id": model_run_id,
            "dataset": span_config,
            "load_dataset": load_config,
            "model": model_manifest,
            "runtime": {
                "batch_size": args.batch_size,
            },
            "path": load_config["path"],
            "name": load_config["name"],
            "repo_id": load_config["path"],
            "subset": load_config["name"],
            "split": load_config["split"],
            "language": language,
            "min_silence_span": min_silence_span,
            "adapter_id": adapter.adapter_id,
            "adapter": args.adapter,
            "batch_size": args.batch_size,
            "inference_interval": args.inference_interval,
            "transcript_lag": args.transcript_lag,
            "n_rows": len(prediction_rows),
            "n_spans": len(language_span_rows),
        }
        if skipped_languages:
            manifest["skipped_languages"] = skipped_languages
        if load_config.get("revision") is not None:
            manifest["revision"] = load_config["revision"]
        if display_name is not None:
            manifest["display_name"] = display_name
        if score_point is not None:
            manifest["score_point"] = score_point
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        run_dirs.append(output_dir)
    progress.finish(f"wrote {len(run_dirs)} run dirs")
    return run_dirs


def _run_predict_streaming(args) -> list[Path]:
    return asyncio.run(_run_predict_streaming_async(args))


async def _run_predict_streaming_async(args) -> list[Path]:
    progress_interval = _progress_interval(args)
    adapter = load_streaming_adapter(args.adapter)
    _apply_streaming_overrides(adapter, args)

    concurrency = getattr(args, "concurrency", None)
    if concurrency is None:
        concurrency = int(getattr(adapter, "concurrency", 1))
    if concurrency <= 0:
        raise ValueError("concurrency must be positive")

    token = os.getenv("HF_TOKEN")
    load_config = _load_dataset_config(args)
    if progress_interval is not None:
        revision = f" revision={load_config['revision']}" if load_config.get("revision") is not None else ""
        _log_progress(
            f"predict-streaming: loading dataset {load_config['path']}::{load_config['name']} "
            f"split={load_config['split']}{revision}",
        )
    ds = load_hf_dataset(
        load_config["path"],
        load_config["name"],
        load_config["split"],
        revision=load_config.get("revision"),
        token=token,
    )

    dataset_rows = [dict(row) for row in ds]
    limit = getattr(args, "limit", None)
    if limit is not None:
        if int(limit) <= 0:
            raise ValueError("--limit must be positive.")
        dataset_rows = dataset_rows[: int(limit)]
    if not dataset_rows:
        raise ValueError("Dataset produced no rows for streaming prediction.")

    min_silence_span = DEFAULT_MIN_SILENCE
    span_rows = build_span_set(dataset_rows, min_silence_span=min_silence_span)
    if not span_rows:
        raise ValueError("Dataset produced an empty prediction span set.")
    span_rows_by_language = _group_rows_by_language(span_rows)

    output_root = Path(args.output_dir).expanduser().resolve()
    span_root_config = _span_set_config(args, min_silence_span)
    span_set_root = output_root / _span_set_dir_name(span_root_config)
    model_run_id = _streaming_model_run_dir_name(args.adapter, adapter)
    prediction_config = _streaming_prediction_config(adapter, args)
    output_dirs = {language: span_set_root / language / model_run_id for language in span_rows_by_language}

    span_set_manifests: dict[str, dict[str, Any]] = {}
    for language, language_span_rows in span_rows_by_language.items():
        span_set_dir = span_set_root / language
        span_set_dir.mkdir(parents=True, exist_ok=True)
        span_set_manifests[language] = _write_or_validate_span_set(
            span_set_dir,
            _span_set_config(args, min_silence_span, language=language),
            language_span_rows,
        )

    skipped_languages: dict[str, str] = {}
    languages_to_run: list[str] = []
    overwrite = bool(getattr(args, "overwrite", False))
    for language, output_dir in output_dirs.items():
        if not adapter_supports_language(adapter, language):
            skipped_languages[language] = "unsupported_language"
            continue
        span_config = _span_set_config(args, min_silence_span, language=language)
        if output_dir.exists() and not overwrite:
            if _streaming_model_run_artifact_can_be_reused(
                output_dir,
                span_config=span_config,
                load_config=load_config,
                model_run_id=model_run_id,
                prediction_config=prediction_config,
                span_rows=span_rows_by_language[language],
            ):
                skipped_languages[language] = "existing_predictions"
                continue
            raise FileExistsError(
                f"Streaming model run directory already exists but is incomplete or stale: {output_dir}. "
                "Use --overwrite to replace it.",
            )
        languages_to_run.append(language)

    for language in languages_to_run:
        output_dirs[language].mkdir(parents=True, exist_ok=True)

    if not languages_to_run:
        if progress_interval is not None:
            _log_progress(
                "predict-streaming: nothing to run; "
                f"skipped languages: {_format_skip_summary(skipped_languages)}",
            )
        return []

    languages_to_run_set = set(languages_to_run)
    rows = [row for row in dataset_rows if row_language(row) in languages_to_run_set]
    if not rows:
        if progress_interval is not None:
            _log_progress("predict-streaming: no dataset rows matched runnable languages")
        return []

    semaphore = asyncio.Semaphore(concurrency)
    started = time.perf_counter()
    progress = _ProgressReporter(
        label="predict-streaming",
        total=len(rows),
        unit="turns",
        interval=progress_interval,
    )
    progress.start(
        "languages="
        f"{_format_language_list(languages_to_run)}; "
        f"skipped_languages={_format_skip_summary(skipped_languages)}; "
        f"concurrency={concurrency}",
    )

    async def guarded(row: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            try:
                result = adapter.predict_turn(row, inference_interval=args.inference_interval)
                if inspect.isawaitable(result):
                    result = await result
                return _validate_streaming_result(row, result)
            except Exception as exc:
                if not bool(getattr(args, "skip_errors", False)):
                    raise
                return {
                    "id": row.get("id"),
                    "skipped": True,
                    "language": row.get("language"),
                    "reason": f"error: {type(exc).__name__}: {exc}",
                    "events": [],
                    "prediction_rows": [],
                    "audio_sec": 0.0,
                }

    async def guarded_index(index: int, row: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return index, await guarded(row)

    tasks = [asyncio.create_task(guarded_index(index, row)) for index, row in enumerate(rows)]
    results_by_index: list[dict[str, Any] | None] = [None] * len(rows)
    try:
        for task in asyncio.as_completed(tasks):
            index, result = await task
            results_by_index[index] = result
            progress.advance()
    except Exception:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    results = [result for result in results_by_index if result is not None]
    elapsed = time.perf_counter() - started
    progress.finish("api calls complete")

    prediction_rows_by_language: dict[str, list[dict[str, Any]]] = defaultdict(list)
    event_rows_by_language: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped_rows_by_language: dict[str, list[dict[str, Any]]] = defaultdict(list)
    audio_sec_by_language: dict[str, float] = defaultdict(float)
    scored_turns_by_language: dict[str, int] = defaultdict(int)

    for result in results:
        language = row_language(result)
        if result.get("skipped"):
            skipped_rows_by_language[language].append(
                {
                    "id": result["id"],
                    "language": language,
                    "reason": result.get("reason"),
                },
            )
            continue
        scored_turns_by_language[language] += 1
        audio_sec_by_language[language] += float(result.get("audio_sec", 0.0))
        prediction_rows_by_language[language].extend(
            _ordered_prediction_row(row) for row in result["prediction_rows"]
        )
        for event in result.get("events", []):
            event_rows_by_language[language].append({"id": result["id"], **event})

    run_dirs: list[Path] = []
    display_name = _adapter_display_name(adapter)
    score_point = _adapter_score_point(adapter)
    rows_by_language = _group_rows_by_language(rows)
    for language in languages_to_run:
        prediction_rows = prediction_rows_by_language.get(language, [])
        if not prediction_rows:
            raise RuntimeError(f"Streaming adapter produced no prediction rows for language {language!r}.")

        output_dir = output_dirs[language]
        predictions_path = output_dir / "predictions.parquet"
        events_path = output_dir / "events.parquet"
        manifest_path = output_dir / "manifest.json"
        summary_path = output_dir / "summary.json"

        event_rows = event_rows_by_language.get(language, [])
        skipped_rows = skipped_rows_by_language.get(language, [])

        pd.DataFrame(prediction_rows).to_parquet(predictions_path, index=False)
        pd.DataFrame(event_rows).to_parquet(events_path, index=False)
        if skipped_rows:
            pd.DataFrame(skipped_rows).to_parquet(output_dir / "skipped.parquet", index=False)

        span_config = _span_set_config(args, min_silence_span, language=language)
        span_set_manifest = span_set_manifests[language]
        total_audio_sec = float(audio_sec_by_language.get(language, 0.0))
        manifest = {
            "harness_version": __version__,
            "span_set_id": span_set_manifest["span_set_id"],
            "model_run_id": model_run_id,
            "dataset": span_config,
            "load_dataset": load_config,
            "path": load_config["path"],
            "name": load_config["name"],
            "repo_id": load_config["path"],
            "subset": load_config["name"],
            "split": load_config["split"],
            "language": language,
            "min_silence_span": min_silence_span,
            "adapter_id": adapter.adapter_id,
            "adapter": args.adapter,
            "streaming": True,
            "inference_interval": args.inference_interval,
            "concurrency": concurrency,
            "n_dataset_rows": len(rows_by_language.get(language, [])),
            "n_scored_turns": int(scored_turns_by_language.get(language, 0)),
            "n_skipped_turns": len(skipped_rows),
            "n_rows": len(prediction_rows),
            "n_spans": len(span_rows_by_language[language]),
            "n_event_rows": len(event_rows),
            "total_audio_sec": total_audio_sec,
            "wall_clock_sec": elapsed,
            "audio_x_realtime": (total_audio_sec / elapsed) if elapsed > 0 else None,
            "skip_errors": bool(getattr(args, "skip_errors", False)),
        }
        manifest.update(prediction_config)
        if load_config.get("revision") is not None:
            manifest["revision"] = load_config["revision"]
        if display_name is not None:
            manifest["display_name"] = display_name
        if score_point is not None:
            manifest["score_point"] = score_point
        if skipped_languages:
            manifest["skipped_languages"] = skipped_languages
        if skipped_rows:
            manifest["skipped_reasons"] = sorted({str(row["reason"]) for row in skipped_rows})
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        summary_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        run_dirs.append(output_dir)

    if progress_interval is not None:
        _log_progress(f"predict-streaming: wrote {len(run_dirs)} run dirs")
    return run_dirs


def _apply_streaming_overrides(adapter, args) -> None:
    overrides = {
        "model": getattr(args, "model", None),
        "chunk_ms": getattr(args, "chunk_ms", None),
        "eot_threshold": getattr(args, "eot_threshold", None),
    }
    for attr, value in overrides.items():
        if value is None:
            continue
        if attr == "model" and not str(value).strip():
            raise ValueError("--model must be a non-empty string.")
        if attr == "chunk_ms" and int(value) <= 0:
            raise ValueError("--chunk-ms must be positive.")
        if attr == "eot_threshold" and not 0.0 <= float(value) <= 1.0:
            raise ValueError("--eot-threshold must be in [0, 1].")
        if not hasattr(adapter, attr):
            raise TypeError(f"Adapter {adapter.adapter_id!r} does not support --{attr.replace('_', '-')}.")
        setattr(adapter, attr, value)

    if getattr(args, "skip_unsupported_languages", False) and hasattr(adapter, "skip_unsupported_languages"):
        setattr(adapter, "skip_unsupported_languages", True)


def _validate_streaming_result(row: dict[str, Any], result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise TypeError(f"Streaming adapter returned {type(result).__name__}; expected dict.")

    expected_id = str(row["id"])
    if "id" not in result:
        raise ValueError(f"Streaming adapter result for row {expected_id!r} is missing `id`.")
    if str(result["id"]) != expected_id:
        raise ValueError(f"Streaming adapter returned id {result['id']!r} for row {expected_id!r}.")

    row_language = row.get("language")
    if row_language is None:
        raise ValueError(f"Dataset row {expected_id!r} is missing required `language`.")
    language = str(row_language).strip().lower()
    if not language:
        raise ValueError(f"Dataset row {expected_id!r} has empty `language`.")

    if result.get("skipped"):
        result.setdefault("language", language)
        return result

    result.setdefault("language", language)
    prediction_rows = result.get("prediction_rows")
    if not isinstance(prediction_rows, list):
        raise TypeError(f"Streaming adapter result for row {expected_id!r} must include list `prediction_rows`.")
    if not prediction_rows:
        raise ValueError(f"Streaming adapter result for row {expected_id!r} has empty `prediction_rows`.")
    required = {"id", "language", "span_index", "timestamp", "silence_dur", "p_eot", "label"}
    for index, prediction in enumerate(prediction_rows):
        prediction.setdefault("language", language)
        missing = required - set(prediction)
        if missing:
            raise ValueError(
                f"Prediction row {index} for turn {expected_id!r} is missing required columns: {sorted(missing)}",
            )
        if str(prediction["id"]) != expected_id:
            raise ValueError(
                f"Prediction row {index} for turn {expected_id!r} has mismatched id {prediction['id']!r}.",
            )
        if str(prediction["language"]).strip().lower() != language:
            raise ValueError(
                f"Prediction row {index} for turn {expected_id!r} has mismatched "
                f"language {prediction['language']!r}.",
            )

    events = result.get("events", [])
    if not isinstance(events, list):
        raise TypeError(f"Streaming adapter result for row {expected_id!r} must include list `events` when provided.")
    return result


def _ordered_prediction_row(row: dict[str, Any]) -> dict[str, Any]:
    column_order = ("id", "language", "span_index", "timestamp", "silence_dur", "p_eot", "label")
    ordered = {key: row[key] for key in column_order if key in row}
    ordered.update({key: value for key, value in row.items() if key not in ordered})
    return ordered


def _run_compute_metrics(args) -> None:
    from .metrics import compute_metrics_from_predictions, load_predictions

    predictions_path = Path(args.predictions).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    predictions_df = load_predictions(str(predictions_path))
    manifest = None
    manifest_path = predictions_path.parent / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    score_point = getattr(args, "score_point", None)
    if score_point is None and manifest is not None and manifest.get("score_point") is not None:
        score_point = float(manifest["score_point"])

    tradeoff_df, summary = compute_metrics_from_predictions(
        predictions_df,
        score_point_s=score_point,
        min_hold_span_duration=args.min_hold_span_duration,
        max_hold_span_duration=args.max_hold_span_duration,
    )

    tradeoff_df.to_parquet(output_dir / "tradeoff.parquet", index=False)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "report.html").unlink(missing_ok=True)


def _run_compare_models(args) -> Path:
    from .comparison import write_comparison_report

    return write_comparison_report(
        args.span_set_dir,
        min_hold_span_duration=args.min_hold_span_duration,
        max_hold_span_duration=args.max_hold_span_duration,
    )


def _run_compare_languages(args) -> Path:
    from .comparison import write_language_comparison_report

    return write_language_comparison_report(
        args.span_set_root,
        output_dir=getattr(args, "output_dir", None),
        min_hold_span_duration=args.min_hold_span_duration,
        max_hold_span_duration=args.max_hold_span_duration,
    )
