from __future__ import annotations

from typing import Any


NON_ACCEPTING = {
    "REPAIR_RETRIEVE",
    "REPAIR_CLARIFY",
    "REPAIR_APPROVAL",
    "REJECT_UNSUPPORTED",
    "REJECT_UNSAFE",
    "REJECT_OUT_OF_BOUNDS",
    "UNKNOWN_MODEL_GAP",
    "HALT_OR_DEGRADE",
}


def make_accept_row(row_id: str, candidate_id: str, fixture_id: str, claim_ids: list[str], gate_ids: list[str]) -> dict[str, Any]:
    return {
        "accept_row_id": f"accept-{row_id}",
        "row_id": row_id,
        "candidate_id": candidate_id,
        "fixture_id": fixture_id,
        "claim_ids": claim_ids,
        "gate_ids": gate_ids,
        "required_verifier_ids": [],
        "required_sufficiency_ids": [],
        "ct_results": [],
        "m_gate_results": [],
        "verdict": "UNKNOWN_MODEL_GAP",
        "verdict_scope": "bounded_fixture",
        "blocking_reasons": ["not_reduced"],
        "evidence_refs": [],
        "review_state": "pending",
    }
