"""Closed-fixture benchmark for accepted-result challenge decisions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from ..runtime.acceptance_challenge import challenge_accepted_result


def run_acceptance_challenge_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in load_jsonl(cases_path):
        result = challenge_accepted_result(case["result"], case["policy"], case["evidence_catalog"], case.get("signals", []))
        expected_reasons = set(case.get("expected_reasons", []))
        rows.append({
            "case_id": case["case_id"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "expected_decision": case["expected_decision"],
            "actual_decision": result["decision"],
            "actual_reasons": result["reasons"],
            "case_ok": result["decision"] == case["expected_decision"] and expected_reasons.issubset(result["reasons"]),
        })
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "false_clear_count": sum(row["expected_decision"] in {"CHALLENGE", "BLOCK"} and row["actual_decision"] == "CLEAR" for row in rows),
        "claim": "closed_fixture_accepted_result_challenge_only",
        "blocked_claims": ["semantic_error_detection", "safety_detection", "fairness_detection", "general_quality_judgement"],
    }
    (out / "acceptance_challenge_benchmark_rows.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    (out / "acceptance_challenge_benchmark_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _ratio(values: Any) -> float:
    items = list(values)
    return round(sum(bool(item) for item in items) / len(items), 6) if items else 0.0
