from lce_validation.empirical.quality_discovery_aggregate import run_quality_discovery_aggregate


def test_quality_discovery_aggregate_preserves_limits_without_overpromoting(tmp_path):
    result = run_quality_discovery_aggregate(tmp_path / "aggregate")
    assert result["ok"]
    assert result["promotion"] == "BOUNDED_GO_WITH_LIMITS"
    assert result["wave_count"] == 4
    assert result["total_case_count"] == 42
    assert result["total_unexpected_failure_count"] == 0
    assert result["remaining_safe_limit_targets"] == ["coding_scope"]
