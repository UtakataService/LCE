from lce_validation.runtime.reasoning_comparison_practice import evaluate_reasoning_comparison_practice


def _record():
    return {"premises":[{"premise_id":"p1","statement":"A measured 1.","status":"observed"}],"conclusion":{"statement":"A is selected.","supporting_premise_ids":["p1"],"causal_claim":False},"comparison":{"subjects":["A","B"],"axis":"measured outcome","conditions_aligned":True},"refutation_checks":[{"would_change_conclusion":"A measurement is invalid"}]}


def test_supported_comparable_refutable_reasoning_is_go(): assert evaluate_reasoning_comparison_practice(_record())["decision"] == "GO"
def test_conclusion_requires_known_premise():
    r=_record(); r["conclusion"]["supporting_premise_ids"]=["missing"]
    assert "UNSUPPORTED_CONCLUSION" in evaluate_reasoning_comparison_practice(r)["reasons"]
def test_causal_claim_requires_mechanism_and_alternatives():
    r=_record(); r["conclusion"]["causal_claim"]=True
    assert "CAUSAL_CLAIM_NOT_DISCIPLINED" in evaluate_reasoning_comparison_practice(r)["reasons"]
