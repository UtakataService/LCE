import pytest

from lce_validation.runtime.grading_assurance import GradingAssuranceError, audit_grading_records


def _policy(**overrides):
    value = {
        "policy_id": "writing-rubric-audit-v1",
        "rubric_id": "writing-v1",
        "criteria": [
            {"criterion_id": "accuracy", "max_points": 4, "required_evidence_kinds": ["answer_span"]},
            {"criterion_id": "clarity", "max_points": 2, "required_evidence_kinds": ["answer_span"]},
        ],
        "min_grader_count": 2,
        "min_independent_graders": 2,
        "max_total_score_spread": 1,
        "require_calibration": True,
        "accepted_calibration_ids": ["cal-2026q3"],
    }
    value.update(overrides)
    return value


def _record(grading_id, grader_id, independence_key, **overrides):
    value = {
        "grading_id": grading_id,
        "rubric_id": "writing-v1",
        "grader_id": grader_id,
        "independence_key": independence_key,
        "calibration_id": "cal-2026q3",
        "criterion_scores": [
            {"criterion_id": "accuracy", "points": 4, "evidence_refs": ["answer-1"]},
            {"criterion_id": "clarity", "points": 2, "evidence_refs": ["answer-1"]},
        ],
        "total_score": 6,
        "verdict": "pass",
    }
    value.update(overrides)
    return value


def _catalog():
    return {"answer-1": {"kind": "answer_span"}}


def test_accepts_calibrated_independent_records_that_obey_the_rubric():
    result = audit_grading_records([_record("g1", "grader-a", "team-a"), _record("g2", "grader-b", "team-b")], _policy(), _catalog())
    assert result["decision"] == "ACCEPT"
    assert result["independent_grader_count"] == 2


def test_rejects_arithmetic_or_rubric_coverage_errors():
    arithmetic = audit_grading_records([_record("g1", "grader-a", "team-a", total_score=5), _record("g2", "grader-b", "team-b")], _policy(), _catalog())
    assert arithmetic["decision"] == "REJECT"
    assert "TOTAL_SCORE_ARITHMETIC_MISMATCH" in arithmetic["reasons"]
    missing = audit_grading_records([_record("g1", "grader-a", "team-a", criterion_scores=[{"criterion_id": "accuracy", "points": 4, "evidence_refs": ["answer-1"]}]), _record("g2", "grader-b", "team-b")], _policy(), _catalog())
    assert "RUBRIC_CRITERION_MISSING:clarity" in missing["reasons"]


def test_holds_for_missing_evidence_calibration_or_independent_review():
    missing_evidence = audit_grading_records([_record("g1", "grader-a", "team-a", criterion_scores=[{"criterion_id": "accuracy", "points": 4, "evidence_refs": ["answer-1"]}, {"criterion_id": "clarity", "points": 2, "evidence_refs": []}]), _record("g2", "grader-b", "team-b")], _policy(), _catalog())
    assert missing_evidence["decision"] == "HOLD"
    assert "EVIDENCE_KIND_MISSING:clarity:answer_span" in missing_evidence["reasons"]
    same_group = audit_grading_records([_record("g1", "grader-a", "team-a"), _record("g2", "grader-b", "team-a", calibration_id=None)], _policy(), _catalog())
    assert "INDEPENDENT_GRADER_COUNT_BELOW_POLICY" in same_group["reasons"]
    assert "CALIBRATION_REQUIRED" in same_group["reasons"]


def test_holds_when_valid_graders_disagree_beyond_policy_tolerance():
    other = _record("g2", "grader-b", "team-b", criterion_scores=[{"criterion_id": "accuracy", "points": 2, "evidence_refs": ["answer-1"]}, {"criterion_id": "clarity", "points": 1, "evidence_refs": ["answer-1"]}], total_score=3)
    result = audit_grading_records([_record("g1", "grader-a", "team-a"), other], _policy(), _catalog())
    assert result["decision"] == "HOLD"
    assert "TOTAL_SCORE_DISAGREEMENT_REQUIRES_ADJUDICATION" in result["reasons"]


def test_invalid_record_is_not_silently_audited():
    with pytest.raises(GradingAssuranceError, match="INVALID_CRITERION_SCORE"):
        audit_grading_records([_record("g1", "grader-a", "team-a", criterion_scores=[{"criterion_id": "accuracy", "points": "four"}])], _policy(), _catalog())
