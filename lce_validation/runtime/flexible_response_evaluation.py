"""Exposed contract evaluator for the Flexible Response Envelope shadow slice."""
from __future__ import annotations

from typing import Any, Mapping

from .conversation_contract import ContractError, empty_conversation_state
from .conversation_reducer import reduce_turn


def evaluate_fre_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    required = {"case_id", "turns", "expected"}
    if not isinstance(fixture, Mapping) or required - set(fixture) or not isinstance(fixture["turns"], list) or not fixture["turns"]:
        raise ContractError("INVALID_FRE_FIXTURE")
    state = empty_conversation_state(session_id="fre:" + str(fixture["case_id"]))
    transition: dict[str, Any] | None = None
    for turn in fixture["turns"]:
        if not isinstance(turn, Mapping) or not isinstance(turn.get("text"), str):
            raise ContractError("INVALID_FRE_TURN")
        transition = reduce_turn(state, turn["text"])
        state = transition["state"]
    assert transition is not None
    envelope = transition["flexible_response_envelope"]
    expected = fixture["expected"]
    checks = {
        "mode": envelope["mode"] == expected["mode"],
        "claim_class": envelope["claim_class"] == expected["claim_class"],
        "risk_class": envelope["risk_class"] == expected["risk_class"],
        "step_allowed": transition["plan"]["response_steps"][0]["kind"] in envelope["allowed_response_steps"],
        "prohibited_uses": set(expected.get("prohibited_uses", [])) <= set(envelope["prohibited_uses"]),
    }
    return {"case_id": fixture["case_id"], "passed": all(checks.values()), "checks": checks, "envelope": envelope}


def evaluate_fre_bank(fixtures: list[Mapping[str, Any]]) -> dict[str, Any]:
    results = [evaluate_fre_fixture(fixture) for fixture in fixtures]
    low_risk_unknown = [item for item in results if item["envelope"]["mode"] == "UNKNOWN" and item["envelope"]["risk_class"] == "R0_LOW"]
    return {
        "scope": "exposed_fre_shadow",
        "case_count": len(results),
        "passed": sum(item["passed"] for item in results),
        "failed": sum(not item["passed"] for item in results),
        "safe_flexibility_count": sum({"reflect", "clarify", "offer_choice"} <= set(item["envelope"]["allowed_response_steps"]) for item in low_risk_unknown),
        "low_risk_unknown_count": len(low_risk_unknown),
        "claim_boundary": "Exposed shadow-contract evidence only; it does not establish general dialogue quality or blind generalization.",
        "results": results,
    }
