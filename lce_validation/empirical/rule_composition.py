from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .rule_grounding import evaluate_action, parse_rule


DECISION_STRENGTH = {
    "CLARIFY_RULE": 100,
    "DENY": 90,
    "REQUIRE_LOG": 70,
    "REQUIRE_EVIDENCE": 60,
    "ASK_CONFIRMATION": 50,
    "ALLOW": 0,
}


def compose_rules(rules: list[dict[str, Any]], action: dict[str, Any], default_policy: str = "ALLOW") -> dict[str, Any]:
    evaluations = []
    for item in rules:
        parsed = parse_rule(item["rule_text"])
        decision = evaluate_action(parsed, action)
        evaluations.append({
            "rule_id": item["rule_id"],
            "priority": int(item.get("priority", 0)),
            "rule_text": item["rule_text"],
            "parsed_rule": parsed,
            "decision": decision,
            "triggered": decision["decision"] != "ALLOW",
        })

    matched = [row for row in evaluations if row["decision"]["reason"] != "rule subject does not match action"]
    triggered = [row for row in evaluations if row["triggered"]]
    if not triggered:
        if matched:
            return _composition_result("ALLOW", None, evaluations, "matching rules were evaluated and no blocking condition triggered")
        return _composition_result(default_policy, None, evaluations, f"default policy {default_policy} applied")

    top_priority = max(row["priority"] for row in triggered)
    top = [row for row in triggered if row["priority"] == top_priority]
    top_decisions = {row["decision"]["decision"] for row in top}
    if len(top_decisions) > 1:
        return _composition_result("CONFLICT", None, evaluations, "same-priority rules produced different blocking gates")

    winner = sorted(top, key=lambda row: DECISION_STRENGTH.get(row["decision"]["decision"], 0), reverse=True)[0]
    return _composition_result(winner["decision"]["decision"], winner["rule_id"], evaluations, winner["decision"]["reason"])


def run_rule_composition_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in load_jsonl(cases_path):
        result = compose_rules(case["rules"], case["action"], case.get("default_policy", "ALLOW"))
        decision_ok = result["decision"] == case["expected_decision"]
        winner_ok = result.get("winning_rule_id") == case.get("expected_winning_rule_id")
        rows.append({
            "case_id": case["case_id"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "expected_decision": case["expected_decision"],
            "actual_decision": result["decision"],
            "expected_winning_rule_id": case.get("expected_winning_rule_id"),
            "actual_winning_rule_id": result.get("winning_rule_id"),
            "decision_ok": decision_ok,
            "winner_ok": winner_ok,
            "case_ok": decision_ok and winner_ok,
            "composition": result,
        })
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "decision_accuracy": _ratio(row["decision_ok"] for row in rows),
        "winner_accuracy": _ratio(row["winner_ok"] for row in rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "by_tag": _by_tag(rows),
        "claim": "bounded_multirule_composition_only",
        "blocked_claims": [
            "general_policy_reasoning",
            "open_ended_conflict_resolution",
            "legal_reasoning",
            "japanese_rule_grounding",
            "transformer_replacement",
        ],
    }
    _write_jsonl(out / "rule_composition_rows.jsonl", rows)
    (out / "rule_composition_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _composition_result(decision: str, winning_rule_id: str | None, evaluations: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    return {
        "decision": decision,
        "winning_rule_id": winning_rule_id,
        "reason": reason,
        "triggered_rule_ids": [row["rule_id"] for row in evaluations if row["triggered"]],
        "trace": [
            {
                "rule_id": row["rule_id"],
                "priority": row["priority"],
                "decision": row["decision"]["decision"],
                "reason": row["decision"]["reason"],
            }
            for row in evaluations
        ],
    }


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
