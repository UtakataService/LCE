from lce_validation.empirical.quality_discovery_campaign import run_quality_discovery_campaign


def test_quality_discovery_campaign_v2_has_no_unexpected_failures_after_variant_fix(tmp_path):
    result = run_quality_discovery_campaign("lce_validation/fixtures/quality_discovery_v2.jsonl", tmp_path / "campaign")
    assert result["ok"]
    assert result["case_count"] == 8
    assert result["pass_count"] == 7
    assert result["safe_limit_count"] == 1
    assert len(result["safe_limit_ledger"]) == 1
