from __future__ import annotations

from typing import Any


def verifier_result(verifier_id: str, row_id: str, result: str, reason: str) -> dict[str, Any]:
    return {
        "verifier_result_id": f"{verifier_id}-{row_id}",
        "verifier_id": verifier_id,
        "row_id": row_id,
        "input_refs": [],
        "raw_evidence_refs": [],
        "dependency_state": "unknown",
        "result": result,
        "reason": reason,
        "confidence_label": "not_calibrated",
        "known_gaps": [] if result == "pass" else [reason],
    }


def sufficiency_result(sufficiency_id: str, row_id: str, result: str, reason: str) -> dict[str, Any]:
    return {
        "sufficiency_result_id": f"{sufficiency_id}-{row_id}",
        "sufficiency_id": sufficiency_id,
        "row_id": row_id,
        "evidence_refs": [],
        "result": result,
        "reason": reason,
        "missing_fields": [] if result == "pass" else [reason],
    }
