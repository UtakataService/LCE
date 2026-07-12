from lce_validation.empirical.acceptance_challenge_benchmark import run_acceptance_challenge_benchmark


def test_acceptance_challenge_closed_fixture_benchmark_passes(tmp_path):
    result = run_acceptance_challenge_benchmark("lce_validation/fixtures/acceptance_challenge_benchmark_v1.jsonl", tmp_path / "challenge")
    assert result["ok"]
    assert result["case_count"] == 6
    assert result["case_accuracy"] == 1.0
    assert result["false_clear_count"] == 0
