from __future__ import annotations

import base64
import json
import os
import uuid
from argparse import Namespace
from pathlib import Path
from typing import Any

import modal
from dotenv import load_dotenv

from .io import DEFAULT_MIN_SILENCE

DOTENV_PATH = Path(__file__).with_name(".env")
load_dotenv(DOTENV_PATH, override=False)


def _ignore_local_python_source(path: Path) -> bool:
    parts = set(path.parts)
    if "output" in parts or "__pycache__" in parts:
        return True
    return path.suffix != ".py"


COMMON_PACKAGES = (
    "accelerate",
    "datasets>=3.2.0",
    "huggingface_hub>=0.30.0",
    "librosa>=0.10.0",
    "numpy<2",
    "pandas>=2.2.0",
    "peft",
    "pyarrow>=18.0.0",
    "python-dotenv>=1.0.0",
    "s3prl",
    "soundfile>=0.12.1",
)

DEFAULT_IMAGE = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        *COMMON_PACKAGES,
        "onnxruntime-gpu",
        "torch",
        "torchcodec",
        "torchaudio",
        "transformers",
    )
    .add_local_python_source("eot_harness", ignore=_ignore_local_python_source)
)

AUDIO_IMAGE = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg")
    .pip_install(
        *COMMON_PACKAGES,
        "torch==2.5.1",
        "torchaudio==2.5.1",
        "transformers",
    )
    .add_local_python_source("eot_harness", ignore=_ignore_local_python_source)
)

ULTRAVAD_IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .pip_install(
        "accelerate",
        "datasets==4.7.0",
        "huggingface_hub==0.35.3",
        "librosa==0.11.0",
        "numpy<2",
        "pandas>=2.2.0",
        "peft",
        "pyarrow>=18.0.0",
        "s3prl",
        "soundfile==0.13.1",
        "torch==2.7.0",
        "torchcodec",
        "torchaudio==2.7.0",
        "transformers==4.57.0",
    )
    .add_local_python_source("eot_harness", ignore=_ignore_local_python_source)
)

VAP_IMAGE = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "datasets>=3.2.0",
        "huggingface_hub>=0.30.0",
        "numpy<2",
        "pandas>=2.2.0",
        "pyarrow>=18.0.0",
        "python-dotenv>=1.0.0",
        "soundfile>=0.12.1",
        "einops==0.8.1",
        "torch==2.7.0",
        "torchaudio==2.7.0",
        "vap @ git+https://github.com/ErikEkstedt/VoiceActivityProjection.git@f39a78b23a6dccdbedd106e00b48c410b8739f5d",
    )
    .add_local_python_source("eot_harness", ignore=_ignore_local_python_source)
)

HF_VOLUME = modal.Volume.from_name("eot-harness-hf-cache", create_if_missing=True)
VOLUMES = {
    "/root/.cache/huggingface": HF_VOLUME,
}

app = modal.App("eot-harness")


@app.function(image=DEFAULT_IMAGE, gpu="L4", volumes=VOLUMES, timeout=4 * 60 * 60)
def predict_remote_default(config: dict[str, Any]) -> dict[str, Any]:
    return _predict_remote_impl(config)


@app.function(image=AUDIO_IMAGE, gpu="A100-80GB", volumes=VOLUMES, timeout=4 * 60 * 60)
def predict_remote_audio(config: dict[str, Any]) -> dict[str, Any]:
    return _predict_remote_impl(config)


@app.function(image=ULTRAVAD_IMAGE, gpu="L4", volumes=VOLUMES, timeout=15 * 60 * 60)
def predict_remote_ultravad(config: dict[str, Any]) -> dict[str, Any]:
    return _predict_remote_impl(config)


@app.function(image=VAP_IMAGE, gpu="L4", volumes=VOLUMES, timeout=15 * 60 * 60)
def predict_remote_vap(config: dict[str, Any]) -> dict[str, Any]:
    return _predict_remote_impl(config)


REMOTE_PRESETS = {
    "default": predict_remote_default,
    "audio": predict_remote_audio,
    "ultravad": predict_remote_ultravad,
    "vap": predict_remote_vap,
}


def _predict_remote_impl(config: dict[str, Any]) -> dict[str, Any]:
    hf_token = str(config.get("hf_token") or "").strip()
    if not hf_token:
        raise RuntimeError("config must include non-empty `hf_token` for remote prediction")
    os.environ["HF_TOKEN"] = hf_token

    from eot_harness.cli import _run_predict

    output_root = Path("/tmp") / f"eot-harness-{uuid.uuid4().hex}"
    run_dirs = _run_predict(_predict_namespace(config, output_root))
    return _read_prediction_payload(output_root, run_dirs)


def _predict_namespace(config: dict[str, Any], output_dir: Path) -> Namespace:
    path = config.get("path") or config.get("repo_id")
    name = config.get("name") or config.get("subset")
    missing = []
    if not path:
        missing.append("path")
    if not name:
        missing.append("name")
    if not config.get("adapter"):
        missing.append("adapter")
    if missing:
        raise ValueError(f"prediction config missing required keys: {missing}")

    return Namespace(
        path=str(path),
        name=str(name),
        repo_id=str(path),
        subset=str(name),
        split=str(config.get("split", "validation")),
        revision=str(config["revision"]) if config.get("revision") is not None else None,
        adapter=str(config["adapter"]),
        output_dir=str(output_dir),
        min_silence_span=float(config.get("min_silence_span", DEFAULT_MIN_SILENCE)),
        batch_size=int(config.get("batch_size", 128)),
        inference_interval=float(config.get("inference_interval", 0.1)),
        transcript_lag=float(config.get("transcript_lag", 0.5)),
        overwrite=bool(config.get("overwrite", False)),
    )


def _read_prediction_payload(output_root: Path, run_dirs: Path | list[Path]) -> dict[str, Any]:
    if isinstance(run_dirs, Path):
        run_dir_list = [run_dirs]
    else:
        run_dir_list = list(run_dirs)
    if not run_dir_list:
        raise RuntimeError("remote prediction did not return any run directories")

    runs = [_read_single_prediction_payload(output_root, run_dir) for run_dir in run_dir_list]
    payload: dict[str, Any] = {"runs": runs}
    if len(runs) == 1:
        payload.update(runs[0])
    return payload


def _read_single_prediction_payload(output_root: Path, run_dir: Path) -> dict[str, str]:
    predictions_path = run_dir / "predictions.parquet"
    manifest_path = run_dir / "manifest.json"
    missing = [str(path) for path in (predictions_path, manifest_path) if not path.exists()]
    if missing:
        raise RuntimeError(f"remote prediction did not write required artifacts: {missing}")
    payload = {
        "relative_output_dir": str(run_dir.relative_to(output_root)),
        "predictions_b64": base64.b64encode(predictions_path.read_bytes()).decode("ascii"),
        "manifest_json": manifest_path.read_text(encoding="utf-8"),
    }
    span_set_dir = run_dir.parent
    span_set_path = span_set_dir / "span_set.parquet"
    span_manifest_path = span_set_dir / "span_set_manifest.json"
    if span_set_path.exists():
        payload["span_set_b64"] = base64.b64encode(span_set_path.read_bytes()).decode("ascii")
    if span_manifest_path.exists():
        payload["span_set_manifest_json"] = span_manifest_path.read_text(encoding="utf-8")
    return payload


def _write_prediction_payload(payload: dict[str, Any], output_dir: Path) -> list[Path]:
    run_payloads = payload.get("runs")
    if run_payloads is None:
        run_payloads = [payload]
    if not isinstance(run_payloads, list) or not run_payloads:
        raise ValueError("remote payload must include a non-empty `runs` list")

    return [_write_single_prediction_payload(run_payload, output_dir) for run_payload in run_payloads]


def _write_single_prediction_payload(payload: dict[str, str], output_dir: Path) -> Path:
    required = ("relative_output_dir", "predictions_b64", "manifest_json")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"remote payload missing required keys: {missing}")
    run_dir = output_dir / str(payload["relative_output_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    if "span_set_b64" in payload:
        (run_dir.parent / "span_set.parquet").write_bytes(base64.b64decode(payload["span_set_b64"]))
    if "span_set_manifest_json" in payload:
        (run_dir.parent / "span_set_manifest.json").write_text(
            str(payload["span_set_manifest_json"]),
            encoding="utf-8",
        )
    (run_dir / "predictions.parquet").write_bytes(base64.b64decode(payload["predictions_b64"]))
    (run_dir / "manifest.json").write_text(str(payload["manifest_json"]), encoding="utf-8")
    return run_dir


def _resolve_local_hf_token(config: dict[str, Any]) -> str:
    token = str(config.get("hf_token") or "").strip()
    if token:
        return token
    token = str(os.getenv("HF_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(f"HF_TOKEN must be set in {DOTENV_PATH}.")
    return token


def _select_remote_preset(config: dict[str, Any], preset: str | None) -> str:
    selected = str(config.get("modal_preset") or preset or "default").strip()
    if selected not in REMOTE_PRESETS:
        raise ValueError(f"unknown Modal preset {selected!r}; expected one of {sorted(REMOTE_PRESETS)}")
    return selected


@app.local_entrypoint()
def run_predict(config_json: str, output_dir: str = "output", preset: str = "default") -> None:
    config = json.loads(config_json)
    if not isinstance(config, dict):
        raise ValueError("config_json must decode to a JSON object")

    config = dict(config)
    config["hf_token"] = _resolve_local_hf_token(config)
    selected_preset = _select_remote_preset(config, preset)
    payload = REMOTE_PRESETS[selected_preset].remote(config)

    out_dir = Path(output_dir).expanduser().resolve()
    run_dirs = _write_prediction_payload(payload, out_dir)
    response = {
        "output_dirs": [str(run_dir) for run_dir in run_dirs],
        "modal_preset": selected_preset,
    }
    if len(run_dirs) == 1:
        response["output_dir"] = str(run_dirs[0])
    print(
        json.dumps(
            response,
            indent=2,
        ),
    )
