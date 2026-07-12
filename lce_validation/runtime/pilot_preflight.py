"""Fail-closed preflight checks for 100M--3B scaling pilots."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .quality_target import QualityTarget
from .training_data_contract import CorpusManifest


class PilotPreflightError(ValueError):
    pass


ALLOWED_PILOT_TIERS = {100_000_000, 300_000_000, 1_000_000_000, 3_000_000_000}
ALLOWED_TRAINING_MODES = {"scratch", "continued_pretraining", "distillation"}


@dataclass(frozen=True, slots=True)
class PilotPreflight:
    run_id: str
    parameter_count: int
    training_mode: str
    selected_metric_ids: tuple[str, ...]
    declared_variant: str
    corpus_snapshot_hash: str
    target_snapshot_hash: str


def load_pilot_preflight(path: str | Path, *, target: QualityTarget, corpus: CorpusManifest) -> PilotPreflight:
    candidate = Path(path)
    try:
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotPreflightError("UNREADABLE_PILOT_PREFLIGHT") from exc
    return validate_pilot_preflight(raw, target=target, corpus=corpus)


def validate_pilot_preflight(raw: Mapping[str, Any], *, target: QualityTarget, corpus: CorpusManifest) -> PilotPreflight:
    required = {
        "schema_version", "run_id", "parameter_count", "training_mode", "target_snapshot_hash",
        "corpus_snapshot_hash", "declared_variant", "selected_metric_ids", "training_tokens",
        "max_sequence_length", "checkpoint_policy", "stop_conditions",
    }
    if not isinstance(raw, Mapping) or raw.get("schema_version") != "lce-pilot-preflight/v1" or required - set(raw):
        raise PilotPreflightError("INVALID_PILOT_PREFLIGHT_SCHEMA")
    if raw["parameter_count"] not in ALLOWED_PILOT_TIERS:
        raise PilotPreflightError("PILOT_PARAMETER_TIER_NOT_ALLOWED")
    if raw["training_mode"] not in ALLOWED_TRAINING_MODES:
        raise PilotPreflightError("INVALID_PILOT_TRAINING_MODE")
    if raw["target_snapshot_hash"] != target.snapshot_hash or raw["corpus_snapshot_hash"] != corpus.snapshot_hash:
        raise PilotPreflightError("PILOT_PROVENANCE_SNAPSHOT_MISMATCH")
    if raw["declared_variant"] not in target.comparison_variants:
        raise PilotPreflightError("PILOT_VARIANT_NOT_DECLARED")
    metrics = raw["selected_metric_ids"]
    declared_metrics = {metric["metric_id"] for metric in target.metrics}
    if not isinstance(metrics, list) or not metrics or not set(metrics).issubset(declared_metrics):
        raise PilotPreflightError("PILOT_METRICS_NOT_DECLARED")
    if not isinstance(raw["training_tokens"], int) or raw["training_tokens"] <= 0 or not isinstance(raw["max_sequence_length"], int) or raw["max_sequence_length"] < 16:
        raise PilotPreflightError("INVALID_PILOT_TRAINING_BUDGET")
    if not isinstance(raw["checkpoint_policy"], Mapping) or not isinstance(raw["stop_conditions"], list) or not raw["stop_conditions"]:
        raise PilotPreflightError("MISSING_PILOT_RECOVERY_OR_STOP_POLICY")
    return PilotPreflight(
        run_id=raw["run_id"],
        parameter_count=raw["parameter_count"],
        training_mode=raw["training_mode"],
        selected_metric_ids=tuple(raw["selected_metric_ids"]),
        declared_variant=raw["declared_variant"],
        corpus_snapshot_hash=raw["corpus_snapshot_hash"],
        target_snapshot_hash=raw["target_snapshot_hash"],
    )
