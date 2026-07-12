from lce_validation.runtime.conversation_hypothesis_gate import assess_hypothesis
from lce_validation.runtime.flexible_response_envelope import build_flexible_response_envelope, validate_flexible_response_envelope
from lce_validation.runtime.conversation_reducer import reduce_turn
from lce_validation.runtime.conversation_contract import empty_conversation_state


def _assessment(confidence: float) -> dict:
    return assess_hypothesis({"id": "ih:test", "kind": "inferred", "status": "TENTATIVE", "confidence": confidence, "evidence_spans": [{"start": 0, "end": 1}]})


def test_unknown_hypothesis_still_allows_low_risk_conversation_without_claims():
    envelope = build_flexible_response_envelope(precedence="interpretation", frame={"cues": []}, assessments=[_assessment(0.2)], response_step="clarify")
    validate_flexible_response_envelope(envelope)
    assert envelope["mode"] == "UNKNOWN"
    assert envelope["allowed_response_steps"] == ["reflect", "clarify", "offer_choice"]
    assert {"fact_assertion", "directive_advice", "memory_promotion"} <= set(envelope["prohibited_uses"])


def test_hard_safety_lane_overrides_flexibility():
    envelope = build_flexible_response_envelope(precedence="safety", frame={"cues": []}, assessments=[_assessment(0.9)], response_step="boundary", requested_mode="HYPOTHETICAL")
    assert envelope["mode"] == "UNKNOWN"
    assert envelope["allowed_response_steps"] == ["boundary", "clarify"]
    assert "creative_exploration" in envelope["prohibited_uses"]


def test_structured_output_keeps_format_answer_available_without_semantic_claim_promotion():
    envelope = build_flexible_response_envelope(precedence="output_contract", frame={"cues": []}, assessments=[], response_step="answer")
    assert envelope["mode"] == "OBSERVED"
    assert envelope["allowed_response_steps"] == ["answer", "boundary"]
    assert envelope["shadow_response_step_allowed"]
    assert "memory_promotion" in envelope["prohibited_uses"]


def test_reducer_exposes_shadow_envelope_without_replacing_response_step():
    transition = reduce_turn(empty_conversation_state(), "I am tired. Please just listen.")
    assert transition["plan"]["response_steps"][0]["kind"] == "reflect"
    assert transition["flexible_response_envelope"] == transition["plan"]["flexible_response_envelope"]
    assert transition["trace"]["payload"]["fre_mode"] in {"OBSERVED", "UNKNOWN"}
