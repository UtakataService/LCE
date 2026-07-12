import pytest

from lce_validation.empirical.reference_performance import run_reference_performance


def test_reference_performance_emits_bounded_repeated_measurement(tmp_path):
    result = run_reference_performance(tmp_path / "perf", repeats=3)
    assert result["ok"]
    assert result["repeats"] == 3
    assert result["latency_ms"]["p95"] >= result["latency_ms"]["p50"]
    assert result["tracemalloc_peak_bytes"] > 0


def test_reference_performance_rejects_invalid_repeat_count(tmp_path):
    with pytest.raises(ValueError, match="REPEATS_MUST_BE_POSITIVE"):
        run_reference_performance(tmp_path / "perf", repeats=0)
