from lce_validation.runtime.structural_practice_contract import evaluate_structure_practice


def _structure():
    return {"components":[{"component_id":"frame","responsibility":"parse","owner":"runtime","inputs":["text"],"outputs":["frame"]},{"component_id":"policy","responsibility":"decide","owner":"runtime","inputs":["frame"],"outputs":["plan"]}],"dependencies":[{"from":"policy","to":"frame","kind":"uses"}],"invariants":[{"invariant_id":"i1","statement":"policy has frame","verification_ref":"test-policy"}]}


def test_acyclic_owned_structure_is_go(): assert evaluate_structure_practice(_structure())["decision"] == "GO"
def test_cycle_is_no_go():
    s=_structure(); s["dependencies"].append({"from":"frame","to":"policy","kind":"uses"})
    assert "CYCLIC_DEPENDENCY" in evaluate_structure_practice(s)["reasons"]
def test_invariants_require_verification_reference():
    s=_structure(); s["invariants"][0]["verification_ref"]=""
    assert "UNVERIFIED_INVARIANTS" in evaluate_structure_practice(s)["reasons"]
