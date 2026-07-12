from lce_validation.empirical.quality_discovery_campaign import run_quality_discovery_campaign


def test_quality_discovery_campaign_v1_is_clean_after_priority_fix(tmp_path):
    result = run_quality_discovery_campaign("lce_validation/fixtures/quality_discovery_v1.jsonl", tmp_path / "campaign")
    assert result["ok"]
    assert result["case_count"] == 16
    assert result["unexpected_failure_count"] == 0
    assert result["safe_limit_count"] == 1
    assert result["fixture_contracts_satisfied"]
