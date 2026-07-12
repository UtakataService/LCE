"""Versioned quality-target contracts for the 20B-class roadmap.

This module deliberately validates evaluation intent and provenance, not model
quality itself.  A target card prevents an exposed LCE fixture score from being
misreported as a general 20B-class language-model result.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class QualityTargetError(ValueError):
    """Raised when a quality target card cannot support a reproducible claim."""


REQUIRED_TRACKS = {
    "dialogue",
    "knowledge",
    "reasoning",
    "coding",
    "safety",
    "bilingual",
}
REQUIRED_COMPARISON_VARIANTS = {"lce_only", "lm_only", "lm_with_lce"}
ALLOWED_SPLITS = {"development", "validation", "interaction_blind", "sealed"}
ALLOWED_STATUS = {"planned", "running", "complete"}


@dataclass(frozen=True, slots=True)
class QualityTarget:
    target_id: str
    target_version: str
    target_scope: str
    quality_claim_boundary: str
    comparison_variants: tuple[str, ...]
    metrics: tuple[dict[str, Any], ...]
    evaluation_splits: tuple[dict[str, Any], ...]
    release_gates: tuple[dict[str, Any], ...]
    snapshot_hash: str

    def trace_identity(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_version": self.target_version,
            "snapshot_hash": self.snapshot_hash,
            "comparison_variants": list(self.comparison_variants),
        }

    def planned_tracks(self) -> set[str]:
        return {str(metric["track"]) for metric in self.metrics}

    def release_ready(self) -> bool:
        return all(gate["status"] == "complete" for gate in self.release_gates)


def load_quality_target(path: str | Path) -> QualityTarget:
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualityTargetError("UNREADABLE_QUALITY_TARGET") from exc
    return validate_quality_target(raw)


def validate_quality_target(raw: Mapping[str, Any]) -> QualityTarget:
    required = {
        "schema_version",
        "target_id",
        "target_version",
        "target_scope",
        "quality_claim_boundary",
        "comparison_variants",
        "metrics",
        "evaluation_splits",
        "release_gates",
    }
    if not isinstance(raw, Mapping) or raw.get("schema_version") != "lce-quality-target/v1":
        raise QualityTargetError("INVALID_QUALITY_TARGET_SCHEMA")
    if required - set(raw):
        raise QualityTargetError("MISSING_QUALITY_TARGET_FIELDS")
    _validate_identity(raw)
    variants = _validate_variants(raw["comparison_variants"])
    metrics = _validate_metrics(raw["metrics"])
    splits = _validate_splits(raw["evaluation_splits"])
    gates = _validate_gates(raw["release_gates"], splits)
    snapshot_hash = "sha256:" + hashlib.sha256(_canonical_json(dict(raw)).encode("utf-8")).hexdigest()
    return QualityTarget(
        target_id=raw["target_id"],
        target_version=raw["target_version"],
        target_scope=raw["target_scope"],
        quality_claim_boundary=raw["quality_claim_boundary"],
        comparison_variants=variants,
        metrics=metrics,
        evaluation_splits=splits,
        release_gates=gates,
        snapshot_hash=snapshot_hash,
    )


def _validate_identity(raw: Mapping[str, Any]) -> None:
    for field in ("target_id", "target_version", "target_scope", "quality_claim_boundary"):
        if not isinstance(raw[field], str) or not raw[field].strip():
            raise QualityTargetError("INVALID_QUALITY_TARGET_IDENTITY")


def _validate_variants(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or set(value) != REQUIRED_COMPARISON_VARIANTS or len(value) != len(REQUIRED_COMPARISON_VARIANTS):
        raise QualityTargetError("INVALID_COMPARISON_VARIANTS")
    return tuple(sorted(value))


def _validate_metrics(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or not value:
        raise QualityTargetError("INVALID_QUALITY_METRICS")
    tracks: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for metric in value:
        if not isinstance(metric, Mapping) or {"track", "metric_id", "measure", "direction", "split"} - set(metric):
            raise QualityTargetError("INVALID_QUALITY_METRIC")
        if metric["track"] in tracks or metric["track"] not in REQUIRED_TRACKS:
            raise QualityTargetError("INVALID_QUALITY_METRIC_TRACK")
        if metric["direction"] not in {"higher_is_better", "lower_is_better"}:
            raise QualityTargetError("INVALID_QUALITY_METRIC_DIRECTION")
        tracks.add(metric["track"])
        normalized.append(dict(metric))
    if tracks != REQUIRED_TRACKS:
        raise QualityTargetError("MISSING_QUALITY_METRIC_TRACK")
    return tuple(normalized)


def _validate_splits(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or not value:
        raise QualityTargetError("INVALID_EVALUATION_SPLITS")
    names: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for split in value:
        if not isinstance(split, Mapping) or {"name", "custody", "purpose"} - set(split):
            raise QualityTargetError("INVALID_EVALUATION_SPLIT")
        if split["name"] not in ALLOWED_SPLITS or split["name"] in names:
            raise QualityTargetError("INVALID_EVALUATION_SPLIT_NAME")
        names.add(split["name"])
        normalized.append(dict(split))
    if not {"interaction_blind", "sealed"}.issubset(names):
        raise QualityTargetError("MISSING_INDEPENDENT_EVALUATION_SPLIT")
    return tuple(normalized)


def _validate_gates(value: Any, splits: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or not value:
        raise QualityTargetError("INVALID_RELEASE_GATES")
    names: set[str] = set()
    available_splits = {split["name"] for split in splits}
    normalized: list[dict[str, Any]] = []
    for gate in value:
        if not isinstance(gate, Mapping) or {"gate_id", "requires_split", "status", "failure_action"} - set(gate):
            raise QualityTargetError("INVALID_RELEASE_GATE")
        if gate["gate_id"] in names or gate["requires_split"] not in available_splits or gate["status"] not in ALLOWED_STATUS:
            raise QualityTargetError("INVALID_RELEASE_GATE_VALUE")
        names.add(gate["gate_id"])
        normalized.append(dict(gate))
    if not any(gate["requires_split"] == "sealed" for gate in normalized):
        raise QualityTargetError("MISSING_SEALED_RELEASE_GATE")
    return tuple(normalized)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
