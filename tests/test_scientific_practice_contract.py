from copy import deepcopy

from lce_validation.runtime.scientific_practice_contract import evaluate_scientific_practice


def _inquiry(method):
    return {
        "inquiry_id": "i-1",
        "question": "What follows within the declared scope?",
        "claims": [{"claim_id": "c-1", "evidence_refs": ["e-1"]}],
        "assumptions": ["bounded input"],
        "scope": ["demonstration only"],
        "uncertainty": ["semantic truth is not validated"],
        "evidence": [{"evidence_id": "e-1", "kind": "record", "summary": "declared input", "supports": ["c-1"]}],
        "method": method,
    }


def test_mathematics_requires_explicit_proof_obligations():
    method = {"definitions": ["x"], "derivation": ["step"], "proof_obligations": ["show case"], "counterexample_search": ["boundary"]}
    assert evaluate_scientific_practice("mathematics", _inquiry(method))["decision"] == "GO"
    method.pop("proof_obligations")
    result = evaluate_scientific_practice("mathematics", _inquiry(method))
    assert result["decision"] == "NO_GO"
    assert "MATH_PROOF_OBLIGATIONS_MISSING" in result["reasons"]


def test_physics_requires_variables_and_units():
    method = {"variables": ["velocity"], "units": {"velocity": "m/s"}, "model": "bounded", "predictions": ["p"], "test_plan": ["measure"]}
    assert evaluate_scientific_practice("physics", _inquiry(method))["decision"] == "GO"
    method["units"] = {}
    assert "PHYSICS_UNITS_MISSING" in evaluate_scientific_practice("physics", _inquiry(method))["reasons"]


def test_science_requires_a_falsifier():
    method = {"hypothesis": "h", "falsifiers": ["not observed"], "observations": ["o"], "controls": ["control"], "analysis_plan": "compare"}
    assert evaluate_scientific_practice("science", _inquiry(method))["decision"] == "GO"
    method["falsifiers"] = []
    assert "SCIENCE_FALSIFIERS_MISSING" in evaluate_scientific_practice("science", _inquiry(method))["reasons"]


def test_chemistry_requires_conservation_and_safety_boundaries():
    method = {"species": ["A"], "conditions": ["ambient"], "conservation_checks": ["mass"], "measurement_plan": ["observe"], "safety_boundary": "no execution"}
    assert evaluate_scientific_practice("chemistry", _inquiry(method))["decision"] == "GO"
    method["safety_boundary"] = ""
    assert "CHEMISTRY_SAFETY_BOUNDARY_MISSING" in evaluate_scientific_practice("chemistry", _inquiry(method))["reasons"]


def test_biology_requires_variation_and_ethics_boundaries():
    method = {"system": "population", "level_of_organization": "population", "variation_plan": ["replicates"], "controls": ["baseline"], "ethics_boundary": "no organism work"}
    assert evaluate_scientific_practice("biology", _inquiry(method))["decision"] == "GO"
    method["variation_plan"] = []
    assert "BIOLOGY_VARIATION_PLAN_MISSING" in evaluate_scientific_practice("biology", _inquiry(method))["reasons"]


def test_claim_without_traceable_evidence_is_no_go():
    method = {"definitions": ["x"], "derivation": ["step"], "proof_obligations": ["show case"], "counterexample_search": ["boundary"]}
    inquiry = _inquiry(method)
    inquiry["claims"] = deepcopy(inquiry["claims"])
    inquiry["claims"][0]["evidence_refs"] = ["missing"]
    assert "CLAIM_EVIDENCE_GAP" in evaluate_scientific_practice("mathematics", inquiry)["reasons"]
