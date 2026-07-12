from lce_validation.empirical.quality_discovery_campaign import run_quality_discovery_campaign


def test_quality_discovery_campaign_v4_holdout_passes_after_multilingual_repair_fix(tmp_path):
    result = run_quality_discovery_campaign("lce_validation/fixtures/quality_discovery_v4_holdout.jsonl", tmp_path / "campaign")
    assert result["ok"]
    assert result["case_count"] == 10
    assert result["pass_count"] == 9
    assert result["safe_limit_count"] == 1
    assert result["by_split"] == {"holdout_fixed": 10}
    assert all(row["latency_ms"] >= 0 for row in result["priority_backlog"])
