from lce_validation.empirical.public_readiness_evidence import run_public_readiness_evidence


def test_public_readiness_evidence_runs_all_bounded_assurance_suites(tmp_path):
    result = run_public_readiness_evidence(tmp_path / "evidence")
    assert result["ok"]
    assert result["suite_count"] == 3
    assert result["reports"]["candidate_assurance"]["case_count"] == 11
    assert result["reports"]["grading_assurance"]["case_count"] == 7
    assert result["reports"]["acceptance_challenge"]["case_count"] == 6


def test_ci_and_evaluation_policy_keep_public_claims_bounded():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert "run-public-readiness-evidence" in (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Closed fixtures" in (root / "EVALUATION_POLICY.md").read_text(encoding="utf-8")
