from pathlib import Path

from lce_validation.empirical.candidate_assurance_benchmark import run_candidate_assurance_benchmark


CASES = Path("lce_validation/fixtures/candidate_assurance_benchmark_v1.jsonl")


def test_candidate_assurance_benchmark_scores_multidomain_fixture(tmp_path):
    summary = run_candidate_assurance_benchmark(CASES, tmp_path / "candidate")
    assert summary["ok"]
    assert summary["case_count"] == 11
    assert summary["case_accuracy"] == 1.0
    assert summary["false_accept_count"] == 0
