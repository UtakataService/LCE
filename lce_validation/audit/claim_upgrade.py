from __future__ import annotations

from typing import Any


def claim_upgrade_row(claim_id: str, from_status: str, requested_status: str, missing: list[str]) -> dict[str, Any]:
    return {
        "upgrade_row_id": f"upgrade-{claim_id}",
        "claim_id": claim_id,
        "from_status": from_status,
        "requested_status": requested_status,
        "required_evidence_refs": [],
        "actual_evidence_refs": [],
        "missing_evidence": missing,
        "role_approvals": [],
        "decision": "repair_required" if missing else "defer",
        "decision_reason": "missing evidence" if missing else "requires review",
    }
