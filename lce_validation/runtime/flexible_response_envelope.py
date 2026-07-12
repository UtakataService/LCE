"""Pure policy for separating claim permission from conversation flexibility."""
from __future__ import annotations

from typing import Any, Mapping


HARD_PRECEDENCE = {"validation", "privacy", "safety", "deletion"}
MODES = {"OBSERVED", "EXPLORE", "HYPOTHETICAL", "UNKNOWN"}


def build_flexible_response_envelope(*, precedence: str, frame: Mapping[str, Any], assessments: list[Mapping[str, Any]], response_step: str, requested_mode: str | None = None) -> dict[str, Any]:
    """Return a deterministic envelope; it does not render or commit state.

    Admission describes decision support, not truth.  `requested_mode` is a
    structural signal supplied by a future LanguagePack/adapter, never raw text.
    """
    admission = _admission(assessments)
    claim_class = _claim_class(precedence, frame)
    risk_class = _risk_class(precedence, claim_class)
    mode = _mode(precedence, admission, requested_mode)
    allowed_steps = _allowed_steps(precedence, claim_class, admission)
    prohibited_uses = _prohibited_uses(admission, claim_class, risk_class)
    return {
        "schema_version": "flexible-response-envelope/v1",
        "mode": mode,
        "claim_class": claim_class,
        "risk_class": risk_class,
        "admission_snapshot": admission,
        "allowed_response_steps": allowed_steps,
        "prohibited_uses": prohibited_uses,
        "required_markers": _markers(mode),
        "selected_interpretation_ids": [str(item["interpretation_id"]) for item in assessments if item["admission"] == "ELIGIBLE"],
        "withheld_interpretation_ids": [str(item["interpretation_id"]) for item in assessments if item["admission"] != "ELIGIBLE"],
        "trace_reason_codes": [f"precedence:{precedence}", f"admission:{admission}", f"mode:{mode}", f"risk:{risk_class}"],
        "shadow_response_step_allowed": response_step in allowed_steps,
    }


def validate_flexible_response_envelope(envelope: Mapping[str, Any]) -> None:
    required = {"schema_version", "mode", "claim_class", "risk_class", "admission_snapshot", "allowed_response_steps", "prohibited_uses", "required_markers", "selected_interpretation_ids", "withheld_interpretation_ids", "trace_reason_codes", "shadow_response_step_allowed"}
    if not isinstance(envelope, Mapping) or required - set(envelope):
        raise ValueError("INVALID_FRE_ENVELOPE")
    if envelope["schema_version"] != "flexible-response-envelope/v1" or envelope["mode"] not in MODES:
        raise ValueError("INVALID_FRE_ENVELOPE")
    if envelope["admission_snapshot"] not in {"ELIGIBLE", "TENTATIVE_ONLY", "UNKNOWN", "BLOCKED"}:
        raise ValueError("INVALID_FRE_ENVELOPE")
    if not all(isinstance(value, list) for value in (envelope["allowed_response_steps"], envelope["prohibited_uses"], envelope["required_markers"], envelope["selected_interpretation_ids"], envelope["withheld_interpretation_ids"], envelope["trace_reason_codes"])):
        raise ValueError("INVALID_FRE_ENVELOPE")
    if envelope["admission_snapshot"] != "ELIGIBLE" and envelope["claim_class"] in {"FACT", "ADVICE", "MEMORY"} and "fact_assertion" not in envelope["prohibited_uses"]:
        raise ValueError("FRE_UNCERTAIN_CLAIM_LEAK")


def _admission(assessments: list[Mapping[str, Any]]) -> str:
    states = {item.get("admission") for item in assessments}
    if "ELIGIBLE" in states:
        return "ELIGIBLE"
    if "TENTATIVE_ONLY" in states:
        return "TENTATIVE_ONLY"
    if "UNKNOWN" in states or not states:
        return "UNKNOWN"
    return "BLOCKED"


def _claim_class(precedence: str, frame: Mapping[str, Any]) -> str:
    if precedence == "knowledge":
        return "FACT"
    if "advice_permitted" in frame.get("cues", []):
        return "ADVICE"
    if precedence == "output_contract":
        return "FACT"
    return "INTERACTION"


def _risk_class(precedence: str, claim_class: str) -> str:
    if precedence == "safety":
        return "R4_SAFETY"
    if precedence in {"privacy", "deletion"}:
        return "R3_BOUNDARY"
    if claim_class == "FACT":
        return "R2_FACTUAL"
    if claim_class == "ADVICE":
        return "R1_PERSONAL"
    return "R0_LOW"


def _mode(precedence: str, admission: str, requested_mode: str | None) -> str:
    if precedence == "output_contract":
        return "OBSERVED"
    if precedence in HARD_PRECEDENCE or admission in {"TENTATIVE_ONLY", "UNKNOWN", "BLOCKED"}:
        return "UNKNOWN"
    if requested_mode in {"EXPLORE", "HYPOTHETICAL"}:
        return requested_mode
    return "OBSERVED"


def _allowed_steps(precedence: str, claim_class: str, admission: str) -> list[str]:
    if precedence in HARD_PRECEDENCE:
        return ["boundary", "clarify"]
    if precedence == "output_contract":
        return ["answer", "boundary"]
    if admission in {"UNKNOWN", "TENTATIVE_ONLY", "BLOCKED"}:
        return ["reflect", "clarify", "offer_choice"]
    if claim_class == "FACT":
        return ["answer", "clarify", "boundary"]
    if claim_class == "ADVICE":
        return ["reflect", "clarify", "offer_choice"]
    return ["reflect", "clarify", "offer_choice", "close"]


def _prohibited_uses(admission: str, claim_class: str, risk_class: str) -> list[str]:
    if claim_class == "FACT" and risk_class == "R2_FACTUAL" and admission != "ELIGIBLE":
        prohibited = ["memory_promotion", "fact_assertion", "directive_advice", "high_impact_decision"]
    else:
        prohibited = ["memory_promotion"] if admission != "ELIGIBLE" else []
    if admission != "ELIGIBLE" and claim_class != "FACT":
        prohibited.extend(["fact_assertion", "directive_advice", "high_impact_decision"])
    if risk_class in {"R3_BOUNDARY", "R4_SAFETY"}:
        prohibited.extend(["creative_exploration", "relationship_exclusivity"])
    return sorted(set(prohibited))


def _markers(mode: str) -> list[str]:
    if mode == "EXPLORE":
        return ["possibility_marker"]
    if mode == "HYPOTHETICAL":
        return ["hypothetical_marker"]
    if mode == "UNKNOWN":
        return ["uncertainty_boundary"]
    return []
