import json
from pathlib import Path

from lce_validation.runtime.conversation_evaluation import evaluate_axis_bank, evaluate_axis_case, validate_axis_fixture


def _fixtures() -> list[dict]:
    path = Path("lce_validation/fixtures/conversation_orchestrator_phase4b_axes.jsonl")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_axis_fixtures_are_valid_and_cover_both_languages():
    fixtures = _fixtures()
    assert len(fixtures) == 18
    assert {fixture["case_id"].rsplit("-", 1)[1] for fixture in fixtures} == {"en", "ja"}
    for fixture in fixtures:
        validate_axis_fixture(fixture)


def test_axis_evaluator_reports_separate_contract_axes():
    report = evaluate_axis_bank(_fixtures())
    assert report["scope"] == "exposed_axis_lineage"
    assert report["case_count"] == 18
    assert set(report["axes"]) == {"precedence", "response_step", "forbidden_policy", "state_delta", "evidence"}
    assert all(item["passed"] == all(item["matches"].values()) for item in report["results"])


def test_known_listening_case_has_a_fully_explicit_axis_result():
    result = evaluate_axis_case(_fixtures()[0])
    assert result["actual"]["precedence"] == "frame"
    assert result["actual"]["response_step"] == "reflect"
    assert result["actual"]["forbidden_set"] == ["unwanted_advice"]
