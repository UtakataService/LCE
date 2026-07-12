from lce_validation.runtime.design_practice_contract import evaluate_design_practice


def _design():
    return {"design_id":"d1","problem":"Need a bounded component.","goals":["validate"],"non_goals":["general AI"],"constraints":["local"],"alternatives":[{"option_id":"a","summary":"direct","tradeoffs":["simple"]},{"option_id":"b","summary":"layered","tradeoffs":["more code"]}],"decision":{"selected_option_id":"b","rationale":"boundary","rejected_option_ids":["a"],"evidence_refs":["review-1"]},"acceptance_criteria":["tests pass"],"risks":["integration"]}


def test_traceable_design_is_go(): assert evaluate_design_practice(_design())["decision"] == "GO"
def test_design_requires_non_goals():
    d=_design(); d["non_goals"]=[]
    assert "DESIGN_SCOPE_NOT_EXPLICIT" in evaluate_design_practice(d)["reasons"]
def test_design_requires_compared_alternatives():
    d=_design(); d["alternatives"]=d["alternatives"][:1]
    assert "ALTERNATIVES_NOT_COMPARED" in evaluate_design_practice(d)["reasons"]
