"""Closed-fixture benchmark for bounded structured assurance decisions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from ..runtime.structured_assurance import StructuredAssurancePolicy, assess_structured_value


def run_structured_assurance_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case in load_jsonl(cases_path):
        result = assess_structured_value(
            case["value"],
            StructuredAssurancePolicy.from_dict(case["policy"]),
            case.get("evidence_claims", {}),
        )
        actual_status = "ACCEPTED" if result["accepted"] else "SEMANTIC_REJECTED"
        expected_status = case["expected_status"]
        expected_violations = set(case.get("expected_violations", []))
        row = {
            "case_id": case["case_id"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "expected_status": expected_status,
            "actual_status": actual_status,
            "expected_violations": sorted(expected_violations),
            "actual_violations": result["violations"],
            "status_ok": actual_status == expected_status,
            "violations_ok": expected_violations.issubset(result["violations"]),
            "case_ok": actual_status == expected_status and expected_violations.issubset(result["violations"]),
        }
        rows.append(row)
    rejected = [row for row in rows if row["expected_status"] == "SEMANTIC_REJECTED"]
    accepted = [row for row in rows if row["expected_status"] == "ACCEPTED"]
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "rejection_recall": _ratio(row["actual_status"] == "SEMANTIC_REJECTED" for row in rejected),
        "acceptance_recall": _ratio(row["actual_status"] == "ACCEPTED" for row in accepted),
        "false_accept_count": sum(row["expected_status"] == "SEMANTIC_REJECTED" and row["actual_status"] == "ACCEPTED" for row in rows),
        "false_reject_count": sum(row["expected_status"] == "ACCEPTED" and row["actual_status"] == "SEMANTIC_REJECTED" for row in rows),
        "by_tag": _by_tag(rows),
        "claim": "closed_fixture_structured_assurance_only",
        "blocked_claims": [
            "general_intent_fidelity",
            "natural_language_entailment",
            "factual_truth",
            "authorization_guarantee",
            "model_quality_parity",
        ],
    }
    _write_jsonl(out / "structured_assurance_benchmark_rows.jsonl", rows)
    (out / "structured_assurance_benchmark_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _ratio(values: Any) -> float:
    items = list(values)
    return round(sum(bool(item) for item in items) / len(items), 6) if items else 0.0


def _by_tag(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        for tag in row["phenomenon_tags"]:
            entry = result.setdefault(tag, {"case_count": 0, "case_ok": 0})
            entry["case_count"] += 1
            entry["case_ok"] += int(row["case_ok"])
    for entry in result.values():
        entry["accuracy"] = round(entry["case_ok"] / entry["case_count"], 6)
    return result


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
