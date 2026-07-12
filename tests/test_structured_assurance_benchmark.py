from pathlib import Path

from lce_validation.empirical.structured_assurance_benchmark import run_structured_assurance_benchmark


CASES = Path("lce_validation/fixtures/structured_assurance_benchmark_v1.jsonl")


def test_structured_assurance_benchmark_scores_closed_fixture(tmp_path):
    summary = run_structured_assurance_benchmark(CASES, tmp_path / "assurance")
    assert summary["ok"]
    assert summary["case_count"] == 8
    assert summary["case_accuracy"] == 1.0
    assert summary["rejection_recall"] == 1.0
    assert summary["false_accept_count"] == 0
    assert (tmp_path / "assurance" / "structured_assurance_benchmark_summary.json").exists()
