from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .engine import load_jsonl


ACTION_ALIASES = {
    "delete files": "delete_file",
    "delete file": "delete_file",
    "answer": "answer_question",
    "answer from evidence": "answer_question",
    "sending external messages": "send_external_message",
    "external messages": "send_external_message",
    "send external messages": "send_external_message",
    "high risk operations": "high_risk_operation",
    "high risk operation": "high_risk_operation",
}


def parse_rule(rule_text: str) -> dict[str, Any]:
    text = _normalize(rule_text)
    if "do not" in text and "unless approval is present" in text:
        return _rule("prohibition", _find_action(text, default="unknown"), "approval_present == false", "DENY", rule_text)
    if text.startswith("only answer from evidence") or "only answer from evidence" in text:
        return _rule("evidence_requirement", "answer_question", "evidence_present == false", "REQUIRE_EVIDENCE", rule_text)
    if text.startswith("ask confirmation before") or "ask confirmation before" in text:
        return _rule("confirmation_requirement", _find_action(text, default="unknown"), "user_confirmed == false", "ASK_CONFIRMATION", rule_text)
    if text.startswith("always log high risk"):
        return _rule("obligation", "high_risk_operation", "risk == high and log_written == false", "REQUIRE_LOG", rule_text)
    return _rule("ambiguous", "unknown", "ambiguous", "CLARIFY_RULE", rule_text, confidence=0.2)


def evaluate_action(rule: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    if rule["rule_type"] == "ambiguous":
        return _decision(rule, action, "CLARIFY_RULE", "rule text is too vague to execute safely")
    if not _action_matches(rule["subject_action"], action.get("action_type", "")):
        return _decision(rule, action, "ALLOW", "rule subject does not match action")
    gate = rule["gate_action"]
    condition = rule["condition"]
    if condition == "approval_present == false" and not action.get("approval_present", False):
        return _decision(rule, action, gate, "approval is required but absent")
    if condition == "evidence_present == false" and not action.get("evidence_present", False):
        return _decision(rule, action, gate, "evidence is required but absent")
    if condition == "user_confirmed == false" and not action.get("user_confirmed", False):
        return _decision(rule, action, gate, "confirmation is required but absent")
    if condition == "risk == high and log_written == false" and action.get("risk") == "high" and not action.get("log_written", False):
        return _decision(rule, action, gate, "high-risk operation must be logged first")
    return _decision(rule, action, "ALLOW", "rule condition is not triggered")


def run_rule_grounding_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case in load_jsonl(cases_path):
        parsed = parse_rule(case["rule_text"])
        decision = evaluate_action(parsed, case["action"])
        expected_rule = case["expected_structured_rule"]
        parse_ok = all(parsed.get(key) == value for key, value in expected_rule.items())
        decision_ok = decision["decision"] == case["expected_decision"]
        rows.append({
            "case_id": case["case_id"],
            "rule_text": case["rule_text"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "parsed_rule": parsed,
            "expected_structured_rule": expected_rule,
            "parse_ok": parse_ok,
            "decision": decision,
            "expected_decision": case["expected_decision"],
            "decision_ok": decision_ok,
            "case_ok": parse_ok and decision_ok,
        })
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "parse_accuracy": _ratio(row["parse_ok"] for row in rows),
        "decision_accuracy": _ratio(row["decision_ok"] for row in rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "by_tag": _by_tag(rows),
        "claim": "bounded_rule_grounding_step1_only",
        "blocked_claims": [
            "general_rule_understanding",
            "legal_policy_reasoning",
            "conflicting_rule_resolution",
            "japanese_rule_grounding",
            "transformer_replacement",
        ],
    }
    _write_jsonl(out / "rule_grounding_rows.jsonl", rows)
    (out / "rule_grounding_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _rule(rule_type: str, subject_action: str, condition: str, gate_action: str, source: str, confidence: float = 0.85) -> dict[str, Any]:
    return {
        "rule_type": rule_type,
        "subject_action": subject_action,
        "condition": condition,
        "gate_action": gate_action,
        "source_text": source,
        "confidence": confidence,
    }


def _decision(rule: dict[str, Any], action: dict[str, Any], decision: str, reason: str) -> dict[str, Any]:
    return {
        "decision": decision,
        "reason": reason,
        "rule_type": rule["rule_type"],
        "subject_action": rule["subject_action"],
        "action_type": action.get("action_type"),
        "trace": [
            f"parsed:{rule['rule_type']}",
            f"condition:{rule['condition']}",
            f"gate:{rule['gate_action']}",
            f"decision:{decision}",
        ],
    }


def _find_action(text: str, default: str) -> str:
    for phrase, action in ACTION_ALIASES.items():
        if phrase in text:
            return action
    return default


def _action_matches(subject_action: str, action_type: str) -> bool:
    return subject_action == action_type or subject_action == "high_risk_operation"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().rstrip("."))


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
