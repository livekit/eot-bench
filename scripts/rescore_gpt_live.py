"""Rescore a GPT-Live run from its saved events, without new API calls.

Rebuilds the `OutputUtterance` events and `predictions.parquet` from the raw
`OutputSpeech` segments, and writes turn-taking stats to the run's
`manifest.json` and `summary.json`. Run `compute-metrics` afterwards.

    python scripts/rescore_gpt_live.py \\
        output/livekit__eot-bench-data__validation__min_silence_100ms/en/gpt_live_adapter__gpt_live_1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from eot_harness.cli import _ordered_prediction_row
from eot_harness.gpt_live_adapter import (
    DEFAULT_MERGE_GAP_S,
    DEFAULT_VOICED_CAP_S,
    score_output_utterances,
    turn_taking_summary,
)
from eot_harness.io import load_hf_dataset
from eot_harness.streaming_stt import build_event_prediction_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path, help="GPT-Live model run directory")
    parser.add_argument("--merge-gap-s", type=float, default=DEFAULT_MERGE_GAP_S)
    parser.add_argument("--voiced-cap-s", type=float, default=DEFAULT_VOICED_CAP_S)
    args = parser.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    events = pd.read_parquet(run_dir / "events.parquet")
    # Turns where the model never spoke have no events; the span set lists every scored turn.
    span_ids = set(pd.read_parquet(run_dir.parent / "span_set.parquet", columns=["id"])["id"])
    rows = _dataset_rows(manifest, span_ids | set(events["id"]))

    raw_events = events[events["event"] != "OutputUtterance"]
    speech_by_id = {
        turn_id: group[["event", "timestamp", "end", "voiced_sec"]].to_dict("records")
        for turn_id, group in raw_events[raw_events["event"] == "OutputSpeech"].groupby("id")
    }
    utterance_records, prediction_records, summaries = [], [], []
    for turn_id, row in rows.items():
        utterances = score_output_utterances(
            row,
            speech_by_id.get(turn_id, []),
            merge_gap_s=args.merge_gap_s,
            voiced_cap_s=args.voiced_cap_s,
        )
        utterance_records += [{"id": turn_id, **utterance} for utterance in utterances]
        prediction_records += [
            _ordered_prediction_row({**prediction, "language": row["language"]})
            for prediction in build_event_prediction_rows(
                row,
                utterances,
                inference_interval=float(manifest["inference_interval"]),
            )
        ]
        summaries.append(turn_taking_summary(row, utterances))

    pd.concat([raw_events, pd.DataFrame(utterance_records)], ignore_index=True).to_parquet(
        run_dir / "events.parquet",
        index=False,
    )
    pd.DataFrame(prediction_records).to_parquet(run_dir / "predictions.parquet", index=False)

    stats = _turn_taking_stats(pd.DataFrame(summaries))
    for name in ("manifest.json", "summary.json"):
        path = run_dir / name
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.pop("overlap_tolerance_s", None)
        payload.update(merge_gap_s=args.merge_gap_s, voiced_cap_s=args.voiced_cap_s, turn_taking=stats)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=2))


def _dataset_rows(manifest: dict, ids: set[str]) -> dict[str, dict]:
    load = manifest["load_dataset"]
    dataset = load_hf_dataset(load["path"], load.get("name"), load["split"], revision=load.get("revision"))
    columns = dataset.select_columns(["id", "language", "silence_spans"])
    rows = {row["id"]: row for row in columns if row["id"] in ids}
    if missing := ids - rows.keys():
        raise ValueError(f"{len(missing)} event ids are missing from the dataset, e.g. {sorted(missing)[:3]}")
    return rows


def _turn_taking_stats(summaries: pd.DataFrame) -> dict:
    offsets = summaries["reply_offset_sec"].dropna().astype(float)
    return {
        "n_turns": int(len(summaries)),
        "interruption_rate": round(float(summaries["interrupted"].mean()), 4),
        "reply_rate": round(len(offsets) / len(summaries), 4),
        "reply_overlap_rate": round(float((offsets < 0).mean()), 4),
        "reply_offset_sec": {
            "mean": round(float(offsets.mean()), 3),
            "p10": round(float(offsets.quantile(0.1)), 3),
            "p50": round(float(offsets.quantile(0.5)), 3),
            "p90": round(float(offsets.quantile(0.9)), 3),
        },
    }


if __name__ == "__main__":
    main()
