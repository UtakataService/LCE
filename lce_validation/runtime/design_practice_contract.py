"""Language-agnostic design-decision practice contract."""
from __future__ import annotations

from typing import Any, Mapping


REQUIRED_DESIGN = {"design_id", "problem", "goals", "non_goals", "constraints", "alternatives", "decision", "acceptance_criteria", "risks"}


def evaluate_design_practice(design: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if not isinstance(design, Mapping) or REQUIRED_DESIGN - set(design):
        return _result(["INCOMPLETE_DESIGN_RECORD"])
    for field in ("goals", "non_goals", "constraints", "alternatives", "acceptance_criteria", "risks"):
        if not isinstance(design[field], list): reasons.append(f"INVALID_{field.upper()}")
    if not isinstance(design["problem"], str) or not design["problem"].strip() or not design["goals"] or not design["non_goals"]:
        reasons.append("DESIGN_SCOPE_NOT_EXPLICIT")
    alternatives = design["alternatives"] if isinstance(design["alternatives"], list) else []
    if len(alternatives) < 2 or any(not isinstance(item, Mapping) or {"option_id", "summary", "tradeoffs"} - set(item) for item in alternatives):
        reasons.append("ALTERNATIVES_NOT_COMPARED")
    decision = design["decision"]
    if not isinstance(decision, Mapping) or {"selected_option_id", "rationale", "rejected_option_ids", "evidence_refs"} - set(decision):
        reasons.append("DECISION_NOT_TRACEABLE")
    elif decision["selected_option_id"] not in {item.get("option_id") for item in alternatives} or not decision["rationale"] or not decision["evidence_refs"]:
        reasons.append("DECISION_NOT_TRACEABLE")
    if not design["acceptance_criteria"]: reasons.append("NO_ACCEPTANCE_CRITERIA")
    return _result(reasons)


def _result(reasons: list[str]) -> dict[str, Any]:
    reasons = sorted(set(reasons))
    return {"decision": "GO" if not reasons else "NO_GO", "reasons": reasons, "claim_boundary": "Design-process evaluation only; implementation correctness requires separate evidence."}
