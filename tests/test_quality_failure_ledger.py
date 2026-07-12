import pytest

from lce_validation.runtime.quality_failure_ledger import summarize_quality_failures, validate_quality_observation


def test_failure_ledger_extracts_lce_false_negative_blocks():
    rows=[
        {"case_id":"c1","variant":"lce_only","outcome":"fail","track":"dialogue","split":"validation","owner":"lce","failure_class":"control_gate_gap"},
        {"case_id":"c1","variant":"lm_only","outcome":"pass","track":"dialogue","split":"validation","owner":"model"},
        {"case_id":"c2","variant":"lce_only","outcome":"fail","track":"knowledge","split":"validation","owner":"lce","failure_class":"knowledge_gap"},
    ]
    summary=summarize_quality_failures(rows)
    assert summary["by_failure_class"]=={"control_gate_gap":1,"knowledge_gap":1}
    assert summary["lce_false_negative_blocks"]==[{"case_id":"c1","recommended_action":"REVIEW_DELEGATION_OR_GATE","lce_owner":"lce"}]


def test_failed_observation_requires_explicit_classification():
    with pytest.raises(ValueError,match="FAILURE_CLASS_REQUIRED"):
        validate_quality_observation({"case_id":"x","variant":"lce_only","outcome":"fail","track":"dialogue","split":"validation","owner":"lce"})
