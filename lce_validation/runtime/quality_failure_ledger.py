"""Auditable failure classification for comparative 20B-quality evaluation."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping


VARIANTS = {"lce_only", "lm_only", "lm_with_lce"}
FAILURE_CLASSES = {"knowledge_gap", "reasoning_gap", "dialogue_state_gap", "instruction_gap", "expression_gap", "control_gate_gap"}
OWNERS = {"lce", "model", "joint", "unknown"}


def validate_quality_observation(row: Mapping[str, Any]) -> dict[str, Any]:
    required = {"case_id", "variant", "outcome", "track", "split", "owner"}
    if not isinstance(row, Mapping) or required - set(row):
        raise ValueError("INVALID_QUALITY_OBSERVATION")
    if row["variant"] not in VARIANTS or row["outcome"] not in {"pass", "fail"} or row["owner"] not in OWNERS:
        raise ValueError("INVALID_QUALITY_OBSERVATION")
    if row["outcome"] == "fail" and row.get("failure_class") not in FAILURE_CLASSES:
        raise ValueError("FAILURE_CLASS_REQUIRED")
    return dict(row)


def summarize_quality_failures(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [validate_quality_observation(row) for row in rows]
    failures = [row for row in normalized if row["outcome"] == "fail"]
    return {"observations": len(normalized), "failures": len(failures), "by_failure_class": dict(sorted(Counter(row["failure_class"] for row in failures).items())), "by_owner": dict(sorted(Counter(row["owner"] for row in failures).items())), "lce_false_negative_blocks": find_lce_false_negative_blocks(normalized), "claim_boundary": "Failure-ledger summary only; it does not establish 20B-class quality or causal root cause."}


def find_lce_false_negative_blocks(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Find cases where LCE-only failed by a control gate but LM-only passed."""
    grouped: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["case_id"]), {})[str(row["variant"])] = row
    findings = []
    for case_id, variants in sorted(grouped.items()):
        lce, lm = variants.get("lce_only"), variants.get("lm_only")
        if lce and lm and lce["outcome"] == "fail" and lce.get("failure_class") == "control_gate_gap" and lm["outcome"] == "pass":
            findings.append({"case_id": case_id, "recommended_action": "REVIEW_DELEGATION_OR_GATE", "lce_owner": lce["owner"]})
    return findings
