"""Closed-fixture benchmark for model-agnostic candidate assurance."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from ..runtime.candidate_assurance import assess_candidate


def run_candidate_assurance_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case in load_jsonl(cases_path):
        result = assess_candidate(case["candidate"], case["policy"], case["evidence_catalog"])
        expected_reasons = set(case.get("expected_reasons", []))
        row = {
            "case_id": case["case_id"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "expected_decision": case["expected_decision"],
            "actual_decision": result["decision"],
            "expected_reasons": sorted(expected_reasons),
            "actual_reasons": result["reasons"],
            "decision_ok": result["decision"] == case["expected_decision"],
            "reasons_ok": expected_reasons.issubset(result["reasons"]),
            "case_ok": result["decision"] == case["expected_decision"] and expected_reasons.issubset(result["reasons"]),
        }
        rows.append(row)
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "hard_reject_recall": _ratio(row["actual_decision"] == "REJECT" for row in rows if row["expected_decision"] == "REJECT"),
        "hold_recall": _ratio(row["actual_decision"] == "HOLD" for row in rows if row["expected_decision"] == "HOLD"),
        "false_accept_count": sum(row["expected_decision"] in {"REJECT", "HOLD"} and row["actual_decision"] in {"ACCEPT", "ACCEPT_WITH_WARNING"} for row in rows),
        "by_tag": _by_tag(rows),
        "claim": "closed_fixture_multimodal_candidate_assurance_only",
        "blocked_claims": ["object_recognition_accuracy", "speaker_identity_accuracy", "game_theory_quality", "npc_behavior_quality", "real_world_truth"],
    }
    _write_jsonl(out / "candidate_assurance_benchmark_rows.jsonl", rows)
    (out / "candidate_assurance_benchmark_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
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
