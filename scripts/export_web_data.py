#!/usr/bin/env python3
"""Flatten the benchmark output into a TypeScript data module for the blog post.

Reads the per-(language, model) Pareto frontiers from the harness `output/`
tree and emits a single typed TS module consumed by the connected interactive
charts in `apps/www`. The web repo has no parquet tooling, so this runs here and
the generated `data.ts` is committed into the web repo.

Usage:
    uv run python scripts/export_web_data.py \
        --output-root output/livekit__eot-bench-data__validation__min_silence_100ms \
        --out path/to/web/apps/www/components/mdx/turn-detector/data.ts

If --output-root is omitted, the single experiment directory under output/ is used.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from typing import Optional

import numpy as np
import pandas as pd

EPS = 1e-9

# Fine silence-timeout sweep for the VAD baseline, matching the harness report
# (eot_harness/comparison.py: _fine_vad_baseline_from_span_set). The coarse
# `policy_type == 'vad'` rows in the tradeoff sweep only land on a few discrete
# timeouts, so they overstate the latency needed to hit a given cut-off budget
# (e.g. 2000 ms vs the published 1600 ms at 5%). These constants are the harness
# `compare-models` defaults the committed output was generated with.
VAD_MIN_HOLD = 0.2
VAD_MAX_HOLD = 5.0
VAD_TABLE_STEP = 0.01

# Display name (manifest.json `display_name`) -> stable key, label, color token.
MODEL_CONFIG: dict[str, dict] = {
    "LiveKit Turn Detector v1": {
        "key": "livekit-v1",
        "label": "LiveKit Turn Detector v1",
        "colorToken": "chart1",
        "isLiveKit": True,
    },
    "LiveKit Turn Detector v1-mini": {
        "key": "livekit-v1-mini",
        "label": "LiveKit Turn Detector v1-mini",
        "colorToken": "chart6",
        "isLiveKit": True,
    },
    "Deepgram Flux": {"key": "deepgram-flux", "label": "Deepgram Flux", "colorToken": "chart3"},
    "ultraVAD": {"key": "ultravad", "label": "ultraVAD", "colorToken": "chart2"},
    "SmartTurn v3.2": {"key": "smart-turn-v3-2", "label": "SmartTurn v3.2", "colorToken": "chart4"},
    "AssemblyAI": {"key": "assemblyai", "label": "AssemblyAI", "colorToken": "chart5"},
    "Soniox": {"key": "soniox", "label": "Soniox", "colorToken": "chart7"},
    "OpenAI GPT Realtime 2": {
        "key": "openai-gpt-realtime-2",
        "label": "OpenAI GPT Realtime 2",
        "colorToken": "chart8",
    },
}

# Silence-only VAD baseline. It is not a model directory — it lives as the
# `policy_type == 'vad'` rows inside every model's tradeoff sweep (identical
# across models), so we extract it once per language and compute its own
# frontier. Rendered as a reference line in the charts.
VAD_CONFIG = {"key": "vad", "label": "VAD baseline", "colorToken": "chartModerate"}

# Static discrimination table, transcribed from the post (not in the parquet).
DISCRIMINATION = [
    {"model": "LiveKit Turn Detector v1", "auc": 0.96, "precision": 0.91, "recall": 0.92, "f1": 0.91},
    {"model": "Deepgram Flux", "auc": 0.92, "precision": 0.91, "recall": 0.74, "f1": 0.82},
    {"model": "ultraVAD", "auc": 0.88, "precision": 0.76, "recall": 0.95, "f1": 0.84},
    {"model": "SmartTurn v3.2", "auc": 0.83, "precision": 0.84, "recall": 0.64, "f1": 0.73},
    {"model": "LiveKit Turn Detector (text)", "auc": 0.74, "precision": 0.82, "recall": 0.61, "f1": 0.70},
]

ENGLISH = "en"


def downsample(points: list[tuple[float, float]], max_points: int) -> list[tuple[float, float]]:
    """Keep endpoints plus an even stride through the middle."""
    n = len(points)
    if n <= max_points:
        return points
    idxs = {0, n - 1}
    step = (n - 1) / (max_points - 1)
    for i in range(max_points):
        idxs.add(round(i * step))
    return [points[i] for i in sorted(idxs)]


def pareto_envelope(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Lower-left envelope of (latency, cutoff): sort by latency, keep running-min cutoff."""
    pts = sorted(pts, key=lambda p: (p[0], p[1]))
    out: list[tuple[float, float]] = []
    best = float("inf")
    for lat, cut in pts:
        if cut < best - 1e-12:
            out.append((lat, cut))
            best = cut
    return out


def _to_rows(pts: list[tuple[float, float]], max_points: int) -> list[list[float]]:
    pts = downsample(pts, max_points)
    return [[round(lat, 3), round(cut, 4)] for lat, cut in pts]


def read_frontier(tradeoff_path: str, max_points: int) -> Optional[list[list[float]]]:
    """Return the model Pareto frontier as [[latencySec, cutoffFraction], ...] sorted by latency."""
    df = pd.read_parquet(tradeoff_path)
    if "is_pareto" in df.columns:
        df = df[df["is_pareto"]]
    df = df.dropna(subset=["mean_latency", "cutoff_rate"])
    if df.empty:
        return None
    df = df.sort_values("mean_latency")
    pts = [(float(r.mean_latency), float(r.cutoff_rate)) for r in df.itertuples()]
    return _to_rows(pts, max_points)


def _fine_vad_points(span_set_path: str) -> Optional[list[tuple[float, float]]]:
    """Fine VAD baseline from hold-span durations: a fixed silence timeout `delay`
    fires after `delay` of silence, so its latency on a true EoT is `delay` and its
    cut-off rate is the fraction of mid-turn hold pauses longer than `delay`. Sweeping
    `delay` reconstructs the same curve the harness report/table use."""
    spans = pd.read_parquet(span_set_path)
    if "label" not in spans.columns or "duration" not in spans.columns:
        return None
    hold = pd.to_numeric(spans.loc[spans["label"] == "hold", "duration"], errors="coerce").dropna()
    hold = hold[(hold >= VAD_MIN_HOLD - EPS) & (hold <= VAD_MAX_HOLD + EPS)].to_numpy(dtype=float)
    if hold.size == 0:
        return None
    grid = np.round(np.arange(VAD_MIN_HOLD, VAD_MAX_HOLD + VAD_TABLE_STEP / 2.0, VAD_TABLE_STEP), 6)
    return [(float(delay), float((hold > float(delay) + EPS).mean())) for delay in grid]


def read_vad_frontier(
    lang_dir: str, tradeoff_path: str, max_points: int
) -> Optional[list[list[float]]]:
    """Silence-only VAD baseline frontier. Prefer the fine span_set sweep (matches the
    harness report); fall back to the coarse `policy_type == 'vad'` rows if the span set
    is unavailable for a language."""
    span_set_path = os.path.join(lang_dir, "span_set.parquet")
    pts: Optional[list[tuple[float, float]]] = None
    if os.path.exists(span_set_path):
        pts = _fine_vad_points(span_set_path)
    if pts is None:
        df = pd.read_parquet(tradeoff_path)
        if "policy_type" not in df.columns:
            return None
        df = df[df["policy_type"] == "vad"].dropna(subset=["mean_latency", "cutoff_rate"])
        if df.empty:
            return None
        pts = [(float(r.mean_latency), float(r.cutoff_rate)) for r in df.itertuples()]
    env = pareto_envelope(pts)
    if not env:
        return None
    return _to_rows(env, max_points)


def display_name_for(model_dir: str) -> Optional[str]:
    manifest_path = os.path.join(model_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return None
    with open(manifest_path) as fh:
        manifest = json.load(fh)
    return manifest.get("display_name")


def resolve_output_root(arg: Optional[str]) -> str:
    if arg:
        return arg
    candidates = [d for d in glob.glob("output/*") if os.path.isdir(d)]
    if len(candidates) != 1:
        raise SystemExit(
            f"Expected exactly one experiment dir under output/, found {candidates}. "
            "Pass --output-root explicitly."
        )
    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-points-en", type=int, default=40)
    parser.add_argument("--max-points-lang", type=int, default=25)
    args = parser.parse_args()

    root = resolve_output_root(args.output_root)
    languages = sorted(
        d for d in os.listdir(root)
        if os.path.isdir(os.path.join(root, d)) and d != "language_comparison" and len(d) <= 3
    )
    if ENGLISH in languages:
        languages = [ENGLISH] + [l for l in languages if l != ENGLISH]

    by_language: dict[str, dict[str, list]] = {}
    seen_keys: dict[str, dict] = {}
    unmatched: set[str] = set()

    for lang in languages:
        lang_dir = os.path.join(root, lang)
        max_points = args.max_points_en if lang == ENGLISH else args.max_points_lang
        per_model: dict[str, list] = {}
        a_tradeoff: Optional[str] = None
        for model_dir in sorted(glob.glob(os.path.join(lang_dir, "*"))):
            if not os.path.isdir(model_dir):
                continue
            tradeoff = os.path.join(model_dir, "metrics", "tradeoff.parquet")
            if not os.path.exists(tradeoff):
                continue
            a_tradeoff = a_tradeoff or tradeoff
            display = display_name_for(model_dir)
            if display is None:
                continue
            cfg = MODEL_CONFIG.get(display)
            if cfg is None:
                unmatched.add(display)
                continue
            frontier = read_frontier(tradeoff, max_points)
            if frontier is None:
                continue
            per_model[cfg["key"]] = frontier
            seen_keys.setdefault(cfg["key"], cfg)
        # Silence-only VAD baseline, extracted once per language from any sweep.
        if a_tradeoff is not None:
            vad_frontier = read_vad_frontier(lang_dir, a_tradeoff, max_points)
            if vad_frontier is not None:
                per_model[VAD_CONFIG["key"]] = vad_frontier
                seen_keys.setdefault(VAD_CONFIG["key"], VAD_CONFIG)
        if per_model:
            by_language[lang] = per_model

    if unmatched:
        print(f"WARNING: unmatched display names (add to MODEL_CONFIG): {sorted(unmatched)}")

    # Models in the canonical MODEL_CONFIG order (VAD baseline last), restricted to seen keys.
    ordered = [cfg for cfg in MODEL_CONFIG.values() if cfg["key"] in seen_keys]
    if VAD_CONFIG["key"] in seen_keys:
        ordered.append(VAD_CONFIG)
    models = []
    for cfg in ordered:
        entry = {"key": cfg["key"], "label": cfg["label"], "colorToken": cfg["colorToken"]}
        if cfg.get("isLiveKit"):
            entry["isLiveKit"] = True
        models.append(entry)

    frontiers = by_language.get(ENGLISH, {})

    data = {
        "models": models,
        "languages": [l for l in languages if l in by_language],
        "frontiers": frontiers,
        "byLanguage": by_language,
        "discrimination": DISCRIMINATION,
    }

    payload = json.dumps(data, separators=(",", ":"))
    ts = (
        "// GENERATED by eot-bench/scripts/export_web_data.py — do not edit by hand.\n"
        "// Regenerate from the benchmark output and copy the result here.\n"
        "import type { TurnDetectorData } from './selection';\n\n"
        f"export const TURN_DETECTOR_DATA: TurnDetectorData = {payload};\n"
    )
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        fh.write(ts)

    print(f"Wrote {args.out}")
    print(f"  models: {[m['key'] for m in models]}")
    print(f"  languages: {data['languages']}")
    print(f"  english frontier sizes: {{ {', '.join(f'{k}: {len(v)}' for k, v in frontiers.items())} }}")


if __name__ == "__main__":
    main()
