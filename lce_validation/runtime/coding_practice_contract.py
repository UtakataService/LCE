"""Language-agnostic engineering-work contracts and release decisions."""
from __future__ import annotations

from typing import Any, Mapping


class CodingPracticeError(ValueError):
    pass


RISK_CLASSES = {"low", "medium", "high"}
REQUIRED_BRIEF = {"task_id", "objective", "behavioral_requirements", "nonfunctional_constraints", "change_boundary", "unknowns", "risk_class"}
REQUIRED_PLAN_STEP = {"step_id", "intent", "affected_surfaces", "verification_refs"}
REQUIRED_VERIFICATION_KINDS = {"positive", "boundary", "negative", "regression"}


def evaluate_coding_work_contract(work: Mapping[str, Any]) -> dict[str, Any]:
    """Assess process evidence without interpreting a programming language."""
    if not isinstance(work, Mapping):
        raise CodingPracticeError("INVALID_CODING_WORK")
    reasons: list[str] = []
    brief = work.get("brief")
    plan = work.get("implementation_plan")
    verification = work.get("verification_plan")
    record = work.get("change_record")
    if not isinstance(brief, Mapping) or REQUIRED_BRIEF - set(brief):
        reasons.append("INCOMPLETE_TASK_BRIEF")
        risk = "high"
    else:
        risk = brief["risk_class"] if brief["risk_class"] in RISK_CLASSES else "high"
        if not all(isinstance(brief[field], list) for field in ("behavioral_requirements", "nonfunctional_constraints", "change_boundary", "unknowns")):
            reasons.append("INVALID_TASK_BRIEF_FIELDS")
        if not brief["objective"] or not brief["behavioral_requirements"] or not brief["change_boundary"]:
            reasons.append("TASK_BRIEF_NOT_ACTIONABLE")
    if not isinstance(plan, list) or not plan:
        reasons.append("MISSING_IMPLEMENTATION_PLAN")
    else:
        for step in plan:
            if not isinstance(step, Mapping) or REQUIRED_PLAN_STEP - set(step) or not step["intent"] or not isinstance(step["affected_surfaces"], list) or not isinstance(step["verification_refs"], list):
                reasons.append("INVALID_IMPLEMENTATION_STEP")
                break
            if not step["affected_surfaces"] or not step["verification_refs"]:
                reasons.append("UNVERIFIED_IMPLEMENTATION_STEP")
                break
    verification_kinds: set[str] = set()
    if not isinstance(verification, list) or not verification:
        reasons.append("MISSING_VERIFICATION_PLAN")
    else:
        for item in verification:
            if not isinstance(item, Mapping) or not isinstance(item.get("kind"), str) or not isinstance(item.get("evidence"), str) or not item["evidence"]:
                reasons.append("INVALID_VERIFICATION_ITEM")
                break
            verification_kinds.add(item["kind"])
        if not REQUIRED_VERIFICATION_KINDS.issubset(verification_kinds):
            reasons.append("INCOMPLETE_VERIFICATION_COVERAGE")
    if not isinstance(record, Mapping) or not isinstance(record.get("changed_surfaces"), list) or not isinstance(record.get("unchanged_surfaces"), list) or not isinstance(record.get("executed_verifications"), list):
        reasons.append("MISSING_CHANGE_EVIDENCE")
    elif not record["executed_verifications"]:
        reasons.append("NO_EXECUTED_VERIFICATION")
    if risk == "high" and (not isinstance(work.get("rollback_or_mitigation"), str) or not work["rollback_or_mitigation"].strip()):
        reasons.append("HIGH_RISK_ROLLBACK_MISSING")
    decision = "GO" if not reasons else "NO_GO"
    return {
        "decision": decision,
        "reasons": sorted(set(reasons)),
        "risk_class": risk,
        "dimensions": {
            "brief_completeness": not any(reason.startswith("INCOMPLETE_TASK") or reason.startswith("INVALID_TASK") or reason == "TASK_BRIEF_NOT_ACTIONABLE" for reason in reasons),
            "scope_discipline": not any(reason in {"MISSING_IMPLEMENTATION_PLAN", "INVALID_IMPLEMENTATION_STEP"} for reason in reasons),
            "verification_coverage": not any("VERIFICATION" in reason for reason in reasons),
            "evidence_completeness": not any(reason in {"MISSING_CHANGE_EVIDENCE", "NO_EXECUTED_VERIFICATION"} for reason in reasons),
            "risk_handling": "HIGH_RISK_ROLLBACK_MISSING" not in reasons,
        },
        "claim_boundary": "Process-contract decision only; it does not prove semantic correctness, security, or production suitability.",
    }
