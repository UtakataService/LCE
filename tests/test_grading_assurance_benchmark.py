from lce_validation.empirical.grading_assurance_benchmark import run_grading_assurance_benchmark


def test_grading_assurance_closed_fixture_benchmark_passes(tmp_path):
    result = run_grading_assurance_benchmark("lce_validation/fixtures/grading_assurance_benchmark_v1.jsonl", tmp_path / "grading")
    assert result["ok"]
    assert result["case_count"] == 7
    assert result["case_accuracy"] == 1.0
    assert result["false_accept_count"] == 0
