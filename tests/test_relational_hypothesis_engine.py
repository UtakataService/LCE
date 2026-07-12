from lce_validation.runtime.relational_hypothesis_engine import run_relational_hypothesis_cycle


def _frame():
    return {"actor":"alpha","action":"op-7","target":"omega","goal":"goal-z","conditions":["ready"],"observations":[],"constraints":[],"action_catalog":{"op-7":{"requires":["ready"],"effects":["state:done"]}}}


def test_opaque_labels_can_produce_accepted_simulation():
    result = run_relational_hypothesis_cycle(_frame())
    assert result["decision"] == "ACCEPT"
    assert result["selected_outcomes"] == ["state:done"]


def test_missing_condition_requests_clarification_without_inventing_outcome():
    frame = _frame(); frame["conditions"] = []
    result = run_relational_hypothesis_cycle(frame)
    assert result["decision"] == "CLARIFY"
    assert result["selected_outcomes"] == []


def test_constraint_conflict_abstains():
    frame = _frame(); frame["constraints"] = ["state:done"]
    result = run_relational_hypothesis_cycle(frame)
    assert result["decision"] == "ABSTAIN"
    assert "CONSTRAINT_CONFLICT:state:done" in result["public_trace"][0]["reason_codes"]


def test_public_trace_is_deterministic_and_has_no_freeform_reasoning():
    first = run_relational_hypothesis_cycle(_frame())
    second = run_relational_hypothesis_cycle(_frame())
    assert first["public_trace"] == second["public_trace"]
    assert all(set(row) == {"hypothesis_id", "kind", "verdict", "reason_codes"} for row in first["public_trace"])
