from lce_validation.runtime.coding_practice_contract import evaluate_coding_work_contract


def _work(risk="low"):
    return {
        "brief": {"task_id": "change-1", "objective": "Return a bounded result.", "behavioral_requirements": ["valid input works"], "nonfunctional_constraints": ["no network"], "change_boundary": ["runtime/module.py"], "unknowns": ["none"], "risk_class": risk},
        "implementation_plan": [{"step_id": "s1", "intent": "add validation", "affected_surfaces": ["runtime/module.py"], "verification_refs": ["v1"]}],
        "verification_plan": [{"kind": kind, "evidence": f"test-{kind}"} for kind in ("positive", "boundary", "negative", "regression")],
        "change_record": {"changed_surfaces": ["runtime/module.py"], "unchanged_surfaces": ["other.py"], "executed_verifications": ["pytest"]},
        "rollback_or_mitigation": "revert the bounded module",
    }


def test_complete_low_risk_work_contract_is_go():
    assert evaluate_coding_work_contract(_work())["decision"] == "GO"


def test_missing_negative_coverage_is_no_go():
    work = _work()
    work["verification_plan"] = [item for item in work["verification_plan"] if item["kind"] != "negative"]
    result = evaluate_coding_work_contract(work)
    assert result["decision"] == "NO_GO"
    assert "INCOMPLETE_VERIFICATION_COVERAGE" in result["reasons"]


def test_high_risk_work_requires_rollback_or_mitigation():
    work = _work("high")
    work.pop("rollback_or_mitigation")
    result = evaluate_coding_work_contract(work)
    assert result["decision"] == "NO_GO"
    assert "HIGH_RISK_ROLLBACK_MISSING" in result["reasons"]
