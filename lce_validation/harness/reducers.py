from __future__ import annotations

from typing import Any


def reduce_acceptance(
    accept_row: dict[str, Any],
    verifier_results: list[dict[str, Any]],
    sufficiency_results: list[dict[str, Any]],
    gate_results: list[dict[str, Any]],
    *,
    attempted_claim_text: str = "",
) -> dict[str, Any]:
    row = dict(accept_row)
    blockers: list[str] = []

    for result in verifier_results:
        if result.get("result") in {"fail", "unknown"}:
            blockers.append(f"{result.get('verifier_id')}={result.get('result')}")

    for result in sufficiency_results:
        if result.get("result") in {"fail", "unknown"}:
            blockers.append(f"{result.get('sufficiency_id')}={result.get('result')}")

    for result in gate_results:
        if result.get("block_condition"):
            blockers.append(f"{result.get('gate_id')} block")

    replacement_terms = ["attention replaced", "transformer unnecessary", "gpu unnecessary", "cpu/pi feasibility"]
    if any(term in attempted_claim_text.lower() for term in replacement_terms):
        blockers.append("red_line_claim_without_row_evidence")
        row["verdict"] = "REJECT_UNSUPPORTED"
    elif blockers:
        row["verdict"] = "UNKNOWN_MODEL_GAP"
    else:
        row["verdict"] = "ACCEPT_CAVEATED"

    row["blocking_reasons"] = blockers
    return row
