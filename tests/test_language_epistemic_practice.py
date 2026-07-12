from lce_validation.runtime.language_epistemic_practice import evaluate_language_epistemic_practice


def _record(action="clarify"):
    return {"claims":[{"claim_id":"c1","text":"The request may need context.","certainty":"inferred","scope":"current turn","support_refs":["turn-1"],"exception_conditions":["additional context may resolve it"]}],"ambiguities":[{"ambiguity_id":"a1","status":"unresolved","needed_information":"target"}],"response_action":action}


def test_unresolved_ambiguity_can_clarify(): assert evaluate_language_epistemic_practice(_record())["decision"] == "GO"
def test_unresolved_ambiguity_cannot_be_answered(): assert "UNRESOLVED_AMBIGUITY_REQUIRES_HOLD" in evaluate_language_epistemic_practice(_record("answer"))["reasons"]
def test_supported_inference_requires_evidence():
    r=_record(); r["claims"][0]["support_refs"]=[]
    assert "SUPPORTED_CLAIM_WITHOUT_EVIDENCE" in evaluate_language_epistemic_practice(r)["reasons"]
