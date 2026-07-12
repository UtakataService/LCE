from lce_validation.empirical.quality_discovery_campaign import run_quality_discovery_campaign


def test_quality_discovery_campaign_v3_independent_split_passes_after_history_contract_fix(tmp_path):
    result = run_quality_discovery_campaign("lce_validation/fixtures/quality_discovery_v3_independent.jsonl", tmp_path / "campaign")
    assert result["ok"]
    assert result["case_count"] == 8
    assert result["by_split"] == {"independent": 8}
    assert result["unexpected_failure_count"] == 0
