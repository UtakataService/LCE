"""Append-only experiment records pinned to a validated quality target."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .quality_target import QualityTarget, QualityTargetError


class ExperimentLedgerError(ValueError):
    """Raised for an unreproducible experiment or a broken ledger chain."""


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    run_id: str
    target_identity: dict[str, Any]
    variant: str
    model: dict[str, Any]
    data: dict[str, Any]
    evaluation: dict[str, Any]
    parent_hash: str | None
    record_hash: str


def make_experiment_record(
    *,
    run_id: str,
    target: QualityTarget,
    variant: str,
    model: Mapping[str, Any],
    data: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    parent_hash: str | None,
) -> dict[str, Any]:
    if not isinstance(run_id, str) or not run_id.strip():
        raise ExperimentLedgerError("INVALID_RUN_ID")
    if variant not in target.comparison_variants:
        raise ExperimentLedgerError("TARGET_VARIANT_NOT_DECLARED")
    normalized = {
        "run_id": run_id,
        "target_identity": target.trace_identity(),
        "variant": variant,
        "model": _validate_model(model),
        "data": _validate_data(data),
        "evaluation": _validate_evaluation(evaluation, target),
        "parent_hash": parent_hash,
    }
    normalized["record_hash"] = _record_hash(normalized)
    return normalized


def append_experiment_record(path: str | Path, record: Mapping[str, Any]) -> None:
    target = Path(path)
    existing = read_experiment_ledger(target)
    audit = verify_experiment_ledger(existing)
    if not audit["valid"]:
        raise ExperimentLedgerError("EXISTING_EXPERIMENT_LEDGER_INVALID")
    expected_parent = existing[-1]["record_hash"] if existing else None
    if record.get("parent_hash") != expected_parent:
        raise ExperimentLedgerError("EXPERIMENT_LEDGER_PARENT_MISMATCH")
    if _record_hash_without_hash(record) != record.get("record_hash"):
        raise ExperimentLedgerError("EXPERIMENT_RECORD_HASH_MISMATCH")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(_canonical_json(dict(record)) + "\n")


def read_experiment_ledger(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    try:
        return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise ExperimentLedgerError("INVALID_EXPERIMENT_LEDGER_JSON") from exc


def verify_experiment_ledger(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    violations: list[str] = []
    parent: str | None = None
    seen_ids: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            violations.append(f"record:{index}:INVALID_RECORD")
            continue
        run_id = record.get("run_id")
        if not isinstance(run_id, str) or run_id in seen_ids:
            violations.append(f"record:{index}:DUPLICATE_OR_INVALID_RUN_ID")
        else:
            seen_ids.add(run_id)
        if record.get("parent_hash") != parent:
            violations.append(f"record:{index}:PARENT_MISMATCH")
        if _record_hash_without_hash(record) != record.get("record_hash"):
            violations.append(f"record:{index}:HASH_MISMATCH")
        parent = record.get("record_hash") if isinstance(record.get("record_hash"), str) else None
    return {"valid": not violations, "violations": violations, "record_count": len(records)}


def release_claim_status(target: QualityTarget, records: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Return a conservative claim boundary without interpreting model scores."""
    audit = verify_experiment_ledger(records)
    covered = {str(record.get("evaluation", {}).get("split")) for record in records if isinstance(record, Mapping)}
    missing = sorted({gate["requires_split"] for gate in target.release_gates if gate["requires_split"] not in covered})
    variants = {str(record.get("variant")) for record in records if isinstance(record, Mapping)}
    ablation_missing = sorted(set(target.comparison_variants) - variants)
    publishable = audit["valid"] and not missing and not ablation_missing and target.release_ready()
    return {
        "publishable": publishable,
        "missing_required_splits": missing,
        "missing_comparison_variants": ablation_missing,
        "target_release_gates_complete": target.release_ready(),
        "claim_boundary": "Do not publish a general 20B-class quality claim." if not publishable else "Target-defined claim may be reviewed; scores still require human audit.",
    }


def _validate_model(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"model_id", "architecture", "parameter_count", "tokenizer_hash", "code_hash", "precision"}
    if not isinstance(value, Mapping) or required - set(value):
        raise ExperimentLedgerError("INVALID_MODEL_PROVENANCE")
    if not isinstance(value["parameter_count"], int) or value["parameter_count"] <= 0:
        raise ExperimentLedgerError("INVALID_MODEL_PARAMETER_COUNT")
    return dict(value)


def _validate_data(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"dataset_snapshot_hash", "license_manifest_hash", "dedup_policy_id", "language_mix"}
    if not isinstance(value, Mapping) or required - set(value):
        raise ExperimentLedgerError("INVALID_DATA_PROVENANCE")
    if not isinstance(value["language_mix"], Mapping) or not value["language_mix"]:
        raise ExperimentLedgerError("INVALID_LANGUAGE_MIX")
    return dict(value)


def _validate_evaluation(value: Mapping[str, Any], target: QualityTarget) -> dict[str, Any]:
    required = {"split", "metric_id", "value", "evaluator_build_hash"}
    if not isinstance(value, Mapping) or required - set(value):
        raise ExperimentLedgerError("INVALID_EVALUATION_PROVENANCE")
    split = value["split"]
    planned = {metric["metric_id"]: metric for metric in target.metrics}
    metric = planned.get(value["metric_id"])
    if metric is None or metric["split"] != split:
        raise ExperimentLedgerError("EVALUATION_NOT_DECLARED_BY_TARGET")
    if not isinstance(value["value"], (int, float)) or isinstance(value["value"], bool):
        raise ExperimentLedgerError("INVALID_EVALUATION_VALUE")
    return dict(value)


def _record_hash(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(dict(value)).encode("utf-8")).hexdigest()


def _record_hash_without_hash(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("record_hash", None)
    return _record_hash(payload)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
