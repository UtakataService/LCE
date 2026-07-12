"""Mechanical readiness checks for a real training runtime.

This module intentionally does not install packages or start training.  It
turns the Phase 2 prerequisites into a fail-closed gate that a future trainer
must pass immediately before its first real model operation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable, Mapping


class TrainingRuntimeReadinessError(ValueError):
    pass


REQUIRED_PACKAGES = ("torch", "tokenizers", "transformers", "datasets", "accelerate", "safetensors")


@dataclass(frozen=True, slots=True)
class TrainingRuntimeSpec:
    spec_id: str
    spec_version: str
    require_cuda: bool
    corpus_path: Path
    tokenizer_path: Path
    checkpoint_dir: Path
    target_snapshot_hash: str
    corpus_snapshot_hash: str


def load_training_runtime_spec(path: str | Path) -> TrainingRuntimeSpec:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrainingRuntimeReadinessError("UNREADABLE_TRAINING_RUNTIME_SPEC") from exc
    return validate_training_runtime_spec(raw, base_dir=source.parent)


def validate_training_runtime_spec(raw: Mapping[str, Any], *, base_dir: str | Path = ".") -> TrainingRuntimeSpec:
    required = {"schema_version", "spec_id", "spec_version", "require_cuda", "corpus_path", "tokenizer_path", "checkpoint_dir", "target_snapshot_hash", "corpus_snapshot_hash"}
    if not isinstance(raw, Mapping) or raw.get("schema_version") != "lce-training-runtime/v1" or required - set(raw):
        raise TrainingRuntimeReadinessError("INVALID_TRAINING_RUNTIME_SPEC")
    if not isinstance(raw["spec_id"], str) or not isinstance(raw["spec_version"], str) or not isinstance(raw["require_cuda"], bool):
        raise TrainingRuntimeReadinessError("INVALID_TRAINING_RUNTIME_IDENTITY")
    if not all(isinstance(raw[field], str) and raw[field] for field in ("corpus_path", "tokenizer_path", "checkpoint_dir", "target_snapshot_hash", "corpus_snapshot_hash")):
        raise TrainingRuntimeReadinessError("INVALID_TRAINING_RUNTIME_PATHS")
    root = Path(base_dir)
    return TrainingRuntimeSpec(
        spec_id=raw["spec_id"], spec_version=raw["spec_version"], require_cuda=raw["require_cuda"],
        corpus_path=root / raw["corpus_path"], tokenizer_path=root / raw["tokenizer_path"], checkpoint_dir=root / raw["checkpoint_dir"],
        target_snapshot_hash=raw["target_snapshot_hash"], corpus_snapshot_hash=raw["corpus_snapshot_hash"],
    )


def assess_training_runtime(
    spec: TrainingRuntimeSpec,
    *,
    package_probe: Callable[[str], bool] | None = None,
    cuda_probe: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    packages = package_probe or _default_package_probe
    cuda = cuda_probe or _default_cuda_probe
    missing_packages = [name for name in REQUIRED_PACKAGES if not packages(name)]
    reasons: list[str] = []
    if missing_packages:
        reasons.append("MISSING_TRAINING_PACKAGES")
    if spec.require_cuda and not cuda():
        reasons.append("CUDA_NOT_AVAILABLE")
    for label, path in (("CORPUS", spec.corpus_path), ("TOKENIZER", spec.tokenizer_path)):
        if not path.is_file() or path.stat().st_size == 0:
            reasons.append(f"{label}_ARTIFACT_MISSING")
    try:
        spec.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        probe = spec.checkpoint_dir / ".lce-write-probe"
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
    except OSError:
        reasons.append("CHECKPOINT_DIRECTORY_NOT_WRITABLE")
    return {
        "ready": not reasons,
        "reasons": sorted(reasons),
        "missing_packages": missing_packages,
        "cuda_available": bool(cuda()),
        "spec_identity": {
            "spec_id": spec.spec_id,
            "spec_version": spec.spec_version,
            "target_snapshot_hash": spec.target_snapshot_hash,
            "corpus_snapshot_hash": spec.corpus_snapshot_hash,
            "spec_hash": _spec_hash(spec),
        },
        "claim_boundary": "Readiness only. A ready result does not prove training success, model quality, or deployment suitability.",
    }


def _default_package_probe(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _default_cuda_probe() -> bool:
    try:
        import torch  # type: ignore[import-not-found]
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _spec_hash(spec: TrainingRuntimeSpec) -> str:
    payload = {
        "spec_id": spec.spec_id, "spec_version": spec.spec_version, "require_cuda": spec.require_cuda,
        "corpus_path": str(spec.corpus_path), "tokenizer_path": str(spec.tokenizer_path), "checkpoint_dir": str(spec.checkpoint_dir),
        "target_snapshot_hash": spec.target_snapshot_hash, "corpus_snapshot_hash": spec.corpus_snapshot_hash,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
