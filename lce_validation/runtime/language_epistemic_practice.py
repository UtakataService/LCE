"""Language, uncertainty, exception, granularity, and safe-hold practice."""
from __future__ import annotations

from typing import Any, Mapping


CERTAINTY = {"observed", "inferred", "unknown"}
RESPONSES = {"answer", "clarify", "abstain", "hold"}


def evaluate_language_epistemic_practice(record: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    claims = record.get("claims") if isinstance(record, Mapping) else None
    ambiguities = record.get("ambiguities") if isinstance(record, Mapping) else None
    response_action = record.get("response_action") if isinstance(record, Mapping) else None
    if not isinstance(claims, list) or not claims:
        reasons.append("MISSING_CLAIMS")
    else:
        for claim in claims:
            required = {"claim_id", "text", "certainty", "scope", "support_refs", "exception_conditions"}
            if not isinstance(claim, Mapping) or required - set(claim):
                reasons.append("INVALID_CLAIM")
                continue
            if claim["certainty"] not in CERTAINTY or not isinstance(claim["text"], str) or not claim["text"].strip() or not isinstance(claim["scope"], str) or not claim["scope"].strip():
                reasons.append("CLAIM_SCOPE_OR_CERTAINTY_INVALID")
            if claim["certainty"] in {"observed", "inferred"} and (not isinstance(claim["support_refs"], list) or not claim["support_refs"]):
                reasons.append("SUPPORTED_CLAIM_WITHOUT_EVIDENCE")
            if claim["certainty"] == "unknown" and response_action == "answer":
                reasons.append("UNKNOWN_ASSERTED_AS_ANSWER")
            if not isinstance(claim["exception_conditions"], list):
                reasons.append("INVALID_EXCEPTION_CONDITIONS")
    if not isinstance(ambiguities, list) or not all(isinstance(item, Mapping) and {"ambiguity_id", "status", "needed_information"} <= set(item) for item in ambiguities):
        reasons.append("INVALID_AMBIGUITY_RECORD")
    elif any(item["status"] == "unresolved" for item in ambiguities) and response_action == "answer":
        reasons.append("UNRESOLVED_AMBIGUITY_REQUIRES_HOLD")
    if response_action not in RESPONSES:
        reasons.append("INVALID_RESPONSE_ACTION")
    return _result(reasons)


def _result(reasons: list[str]) -> dict[str, Any]:
    reasons = sorted(set(reasons))
    return {"decision": "GO" if not reasons else "NO_GO", "reasons": reasons, "claim_boundary": "Language and epistemic hygiene only; factual truth requires independent verification."}
