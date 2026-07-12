from lce_validation.runtime.conversation_hypothesis_gate import assess_hypothesis, selected_interpretation_ids


def _item(*, confidence: float = 0.6, kind: str = "inferred", status: str = "TENTATIVE", evidence: list | None = None) -> dict:
    return {"id": "ih:test", "confidence": confidence, "kind": kind, "status": status, "evidence_spans": [{"start": 0, "end": 1}] if evidence is None else evidence}


def test_supported_inference_and_direct_observation_are_decision_eligible():
    assert assess_hypothesis(_item(confidence=0.55))["admission"] == "ELIGIBLE"
    assert assess_hypothesis(_item(confidence=0.1, kind="observed"))["admission"] == "ELIGIBLE"


def test_tentative_and_unknown_hypotheses_are_not_plan_premises():
    tentative = assess_hypothesis(_item(confidence=0.30))
    unknown = assess_hypothesis(_item(confidence=0.29))
    assert tentative["admission"] == "TENTATIVE_ONLY"
    assert unknown["admission"] == "UNKNOWN"
    assert selected_interpretation_ids([tentative, unknown]) == []


def test_retracted_or_evidence_free_hypotheses_are_blocked_from_use():
    assert assess_hypothesis(_item(status="RETRACTED"))["admission"] == "BLOCKED"
    assert assess_hypothesis(_item(evidence=[]))["admission"] == "UNKNOWN"
