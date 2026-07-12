"""Aggregate bounded Quality Discovery Campaign evidence across V1-V4."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .quality_discovery_campaign import run_quality_discovery_campaign


WAVES = {
    "v1": "quality_discovery_v1.jsonl",
    "v2": "quality_discovery_v2.jsonl",
    "v3": "quality_discovery_v3_independent.jsonl",
    "v4": "quality_discovery_v4_holdout.jsonl",
}


def run_quality_discovery_aggregate(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    results = {wave: run_quality_discovery_campaign(fixtures / filename, out / wave) for wave, filename in WAVES.items()}
    limits = [limit for result in results.values() for limit in result["safe_limit_ledger"]]
    unique_limits: dict[str, dict[str, Any]] = {}
    for limit in limits:
        key = str(limit["reinforcement_target"])
        unique_limits.setdefault(key, limit)
    total_cases = sum(result["case_count"] for result in results.values())
    total_pass = sum(result["pass_count"] for result in results.values())
    total_safe_limits = sum(result["safe_limit_count"] for result in results.values())
    total_failures = sum(result["unexpected_failure_count"] for result in results.values())
    summary = {
        "ok": total_failures == 0,
        "promotion": "BOUNDED_GO_WITH_LIMITS" if total_failures == 0 else "NO_GO",
        "wave_count": len(results),
        "total_case_count": total_cases,
        "total_pass_count": total_pass,
        "total_safe_limit_count": total_safe_limits,
        "total_unexpected_failure_count": total_failures,
        "waves": {wave: {"case_count": result["case_count"], "pass_count": result["pass_count"], "safe_limit_count": result["safe_limit_count"], "unexpected_failure_count": result["unexpected_failure_count"], "latency_ms": result["latency_ms"]} for wave, result in results.items()},
        "remaining_safe_limit_targets": sorted(unique_limits),
        "remaining_safe_limits": list(unique_limits.values()),
        "claim": "fixed_quality_discovery_campaign_aggregate_only",
        "blocked_claims": ["blind_or_sealed_generalization", "general_dialogue_quality", "20b_equivalence", "production_readiness", "external_tool_agent_quality"],
    }
    (out / "quality_discovery_aggregate_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
