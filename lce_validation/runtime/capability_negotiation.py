"""Decide when LCE must deny, handle locally, or defer to a capable model."""
from __future__ import annotations

from typing import Any, Mapping


EXCLUSIVE_LCE_GATES = {"policy_denied", "authorization_missing", "state_conflict", "structured_contract_invalid"}
DEFAULT_NEGOTIATION_PARAMETERS = {"local_confidence_threshold": 0.8, "delegation_bias": 0.0, "model_quality_floor": 0.0}


def negotiate_capability(request: Mapping[str, Any], model_cards: list[Mapping[str, Any]], *, parameters: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Keep LCE-exclusive invariants strict while avoiding capability false negatives."""
    if not isinstance(request, Mapping):
        raise ValueError("INVALID_NEGOTIATION_REQUEST")
    tuning = resolve_negotiation_parameters(parameters)
    gates = set(request.get("hard_gates", []))
    if gates & EXCLUSIVE_LCE_GATES:
        return _result("DENY", None, ["LCE_EXCLUSIVE_GATE:" + item for item in sorted(gates & EXCLUSIVE_LCE_GATES)])
    required = set(request.get("required_capabilities", []))
    if not required or not all(isinstance(item, str) for item in required):
        return _result("CLARIFY", None, ["REQUIRED_CAPABILITIES_UNDECLARED"])
    local = set(request.get("lce_capabilities", []))
    local_confidence = float(request.get("lce_confidence", 0.0))
    threshold = min(1.0, max(0.0, tuning["local_confidence_threshold"] + 0.2 * tuning["delegation_bias"]))
    if required.issubset(local) and local_confidence >= threshold:
        return _result("HANDLE_LOCALLY", None, ["LCE_CAPABILITY_SUFFICIENT"])
    eligible = [card for card in model_cards if card.get("enabled") is True and float(card.get("quality_score", 0)) >= tuning["model_quality_floor"] and required.issubset(set(card.get("capabilities", [])))]
    if eligible:
        selected = sorted(eligible, key=lambda card: (-float(card.get("quality_score", 0)), str(card.get("model_id", ""))))[0]
        return _result("DEFER_TO_MODEL", str(selected["model_id"]), ["MODEL_CAPABILITY_MATCH", "LCE_LOCAL_CAPABILITY_INSUFFICIENT"])
    return _result("CLARIFY", None, ["NO_ELIGIBLE_MODEL", "LCE_LOCAL_CAPABILITY_INSUFFICIENT"])


def resolve_negotiation_parameters(overrides: Mapping[str, Any] | None = None) -> dict[str, float]:
    """Return bounded tuning values; exclusive LCE gates are never tunable."""
    if overrides is not None and not isinstance(overrides, Mapping):
        raise ValueError("INVALID_NEGOTIATION_PARAMETERS")
    result = dict(DEFAULT_NEGOTIATION_PARAMETERS)
    for key, value in (overrides or {}).items():
        if key not in result or not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("INVALID_NEGOTIATION_PARAMETERS")
        result[key] = float(value)
    if not 0 <= result["local_confidence_threshold"] <= 1 or not -1 <= result["delegation_bias"] <= 1 or result["model_quality_floor"] < 0:
        raise ValueError("INVALID_NEGOTIATION_PARAMETERS")
    return result


def assess_delegated_candidate(negotiation: Mapping[str, Any], candidate_checks: Mapping[str, Any]) -> dict[str, Any]:
    """Recheck LCE-owned contracts after the delegated model returns a result."""
    if negotiation.get("decision") != "DEFER_TO_MODEL":
        return {"accepted": False, "decision": "NO_DELEGATED_CANDIDATE", "reasons": ["NEGOTIATION_NOT_DEFERRED"]}
    required = {"structured_output_ok", "policy_ok", "state_ok"}
    if not isinstance(candidate_checks, Mapping) or not required.issubset(candidate_checks):
        return {"accepted": False, "decision": "REJECT_MODEL_CANDIDATE", "reasons": ["CANDIDATE_CHECKS_INCOMPLETE"]}
    failed = sorted(key for key in required if candidate_checks[key] is not True)
    if failed:
        return {"accepted": False, "decision": "REJECT_MODEL_CANDIDATE", "reasons": failed}
    return {"accepted": True, "decision": "ACCEPT_MODEL_CANDIDATE", "model_id": negotiation["model_id"], "reasons": ["LCE_POST_DELEGATION_GATES_PASSED"]}


def _result(decision: str, model_id: str | None, reasons: list[str]) -> dict[str, Any]:
    return {"decision": decision, "model_id": model_id, "reasons": reasons, "claim_boundary": "Capability-card routing only; a model card does not prove task quality or safety."}
