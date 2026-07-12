from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .limited_domain_app import answer_limited_domain


def run_natural_language_benchmark(
    fixtures_path: str | Path,
    benchmark_path: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cases = load_jsonl(benchmark_path)
    rows: list[dict[str, Any]] = []
    for case in cases:
        result = answer_limited_domain(fixtures_path, case["query"])
        route_ok = result["route"] == case["expected_route"]
        outcome_ok = result["outcome"] == case["expected_outcome"]
        expected_fixture = case.get("expected_fixture_id")
        fixture_ok = expected_fixture is None or result.get("matched_fixture_id") == expected_fixture
        rows.append({
            "case_id": case["case_id"],
            "query": case["query"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "expected_route": case["expected_route"],
            "actual_route": result["route"],
            "expected_outcome": case["expected_outcome"],
            "actual_outcome": result["outcome"],
            "expected_fixture_id": expected_fixture,
            "matched_fixture_id": result.get("matched_fixture_id"),
            "route_ok": route_ok,
            "outcome_ok": outcome_ok,
            "fixture_ok": fixture_ok,
            "case_ok": route_ok and outcome_ok and fixture_ok,
            "match_score": result.get("match_score", 0),
            "evidence_refs": result.get("evidence_refs", []),
            "reason": result.get("reason"),
        })
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "route_accuracy": _ratio(row["route_ok"] for row in rows),
        "outcome_accuracy": _ratio(row["outcome_ok"] for row in rows),
        "fixture_match_accuracy": _ratio(row["fixture_ok"] for row in rows),
        "by_tag": _by_tag(rows),
        "claim": "bounded_english_natural_language_benchmark_only",
        "blocked_claims": [
            "general_natural_language_understanding",
            "japanese_language_handling",
            "llm_quality_parity",
            "transformer_replacement",
        ],
    }
    _write_jsonl(out / "natural_language_benchmark_rows.jsonl", rows)
    (out / "natural_language_benchmark_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _ratio(values: Any) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return round(sum(1 for value in vals if value) / len(vals), 6)


def _by_tag(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        for tag in row["phenomenon_tags"]:
            entry = result.setdefault(tag, {"case_count": 0, "case_ok": 0})
            entry["case_count"] += 1
            entry["case_ok"] += 1 if row["case_ok"] else 0
    for entry in result.values():
        entry["accuracy"] = round(entry["case_ok"] / entry["case_count"], 6)
    return result


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
