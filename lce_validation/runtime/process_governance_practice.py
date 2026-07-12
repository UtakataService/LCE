"""Process, purpose, authority/impact, and provenance practice."""
from __future__ import annotations

from typing import Any, Mapping


HIGH_IMPACT = {"irreversible", "external", "sensitive"}


def evaluate_process_governance_practice(record: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    stages = record.get("stages") if isinstance(record, Mapping) else None
    purpose = record.get("purpose") if isinstance(record, Mapping) else None
    authority = record.get("authority_impact") if isinstance(record, Mapping) else None
    provenance = record.get("provenance") if isinstance(record, Mapping) else None
    if not isinstance(stages, list) or not stages or any(not isinstance(item, Mapping) or {"stage_id", "status", "completion_evidence", "depends_on"} - set(item) for item in stages):
        reasons.append("INVALID_PROCESS_STAGES")
    else:
        completed = {item["stage_id"] for item in stages if item["status"] == "complete"}
        for item in stages:
            if item["status"] == "complete" and (not item["completion_evidence"] or not set(item["depends_on"]).issubset(completed)):
                reasons.append("PROCESS_STAGE_EVIDENCE_OR_ORDER_INVALID")
    if not isinstance(purpose, Mapping) or {"original", "current", "drift_detected", "action"} - set(purpose):
        reasons.append("INVALID_PURPOSE_RECORD")
    elif purpose["drift_detected"] and purpose["action"] not in {"hold", "switch"}:
        reasons.append("PURPOSE_DRIFT_NOT_HANDLED")
    if not isinstance(authority, Mapping) or {"actor_authorized", "impact_classes", "rollback_or_mitigation"} - set(authority):
        reasons.append("INVALID_AUTHORITY_RECORD")
    else:
        impacts = set(authority["impact_classes"]) if isinstance(authority["impact_classes"], list) else HIGH_IMPACT
        if impacts & HIGH_IMPACT and (authority["actor_authorized"] is not True or not authority["rollback_or_mitigation"]):
            reasons.append("HIGH_IMPACT_AUTHORITY_OR_MITIGATION_MISSING")
    if not isinstance(provenance, list) or not provenance or any(not isinstance(item, Mapping) or {"source_id", "obtained_at", "status", "license_or_basis"} - set(item) or item["status"] not in {"verified", "candidate", "stale", "unknown"} for item in provenance):
        reasons.append("INVALID_PROVENANCE")
    elif any(item["status"] in {"stale", "unknown"} for item in provenance) and record.get("decision_action") == "execute":
        reasons.append("UNSAFE_EXECUTION_ON_UNCERTAIN_PROVENANCE")
    return _result(reasons)


def _result(reasons: list[str]) -> dict[str, Any]:
    reasons = sorted(set(reasons))
    return {"decision": "GO" if not reasons else "NO_GO", "reasons": reasons, "claim_boundary": "Governance-process evaluation only; legal, policy, and operational approval remain external decisions."}
