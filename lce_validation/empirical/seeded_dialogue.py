from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .nl_normalization import normalize_tokens
from .policy_pack_lifecycle import evaluate_policy_pack


DEFAULT_POLICY_PACK = {
    "policy_pack_id": "seeded-dialogue-safety-v1",
    "schema_version": "policy_pack.v1",
    "version": "1.0.0",
    "lifecycle_status": "active",
    "min_engine_version": "lce-policy-lifecycle-v0",
    "default_policy": "ALLOW",
    "rules": [
        {"rule_id": "delete-approval", "priority": 100, "rule_text": "Do not delete files unless approval is present."},
        {"rule_id": "external-approval", "priority": 100, "rule_text": "Do not send external messages unless approval is present."},
        {"rule_id": "answer-evidence", "priority": 80, "rule_text": "Only answer from evidence when evidence is available."},
        {"rule_id": "external-confirm", "priority": 50, "rule_text": "Ask confirmation before sending external messages."},
    ],
    "blocked_claims": [
        "open_domain_conversation",
        "general_language_understanding",
        "llm_quality_parity",
        "transformer_replacement",
    ],
}


TEMPLATES = {
    "deny": [
        "その操作は承認がないため止めます。必要なら、承認の有無を確認する流れに切り替えます。",
        "承認なしでは進めません。まず安全条件を満たしてから実行判断に戻します。",
    ],
    "require_evidence": [
        "根拠が足りないので断定しません。使える証拠を追加するか、確認質問に切り替えます。",
        "今の入力だけでは証拠不足です。証拠を取得してから答えるのが安全です。",
    ],
    "ask_confirmation": [
        "外部に影響する可能性があります。実行前に確認を取る必要があります。",
        "この操作は確認待ちにします。ユーザー確認が取れたら次へ進めます。",
    ],
    "clarify": [
        "意図がまだ粗いので、対象と目的をもう一段だけ確認したいです。",
        "このままだと判断が曖昧です。何を対象にするかを絞る必要があります。",
    ],
    "continue": [
        "了解です。安全条件に触れていないので、次の小さな処理単位へ進めます。",
        "進められます。まず状態を整理して、必要な出力だけ返す流れにします。",
    ],
}


def respond_from_seed(user_input: str, policy_pack: dict[str, Any] | None = None) -> dict[str, Any]:
    seed = stable_seed(user_input)
    rng = random.Random(seed)
    signal = infer_dialogue_signal(user_input, rng)
    action = build_action(signal)
    pack = policy_pack or DEFAULT_POLICY_PACK
    policy_result = evaluate_policy_pack(pack, action)
    route = route_from_policy(policy_result, signal)
    template = rng.choice(TEMPLATES[route])
    response = {
        "ok": True,
        "input": user_input,
        "seed": seed,
        "route": route,
        "response": template,
        "signal": signal,
        "action": action,
        "policy_decision": policy_result["decision"],
        "policy_reason": policy_result["reason"],
        "trace": [
            f"seed:{seed}",
            f"intent:{signal['intent']}",
            f"risk:{signal['risk']}",
            f"policy:{policy_result['decision']}",
            f"route:{route}",
        ],
        "claim": "bounded_seeded_dialogue_control_only",
        "blocked_claims": [
            "open_domain_conversation",
            "general_language_understanding",
            "emotional_understanding",
            "llm_quality_parity",
            "transformer_replacement",
        ],
    }
    return response


def infer_dialogue_signal(user_input: str, rng: random.Random) -> dict[str, Any]:
    lowered = user_input.lower()
    tokens = normalize_tokens(user_input)
    joined = " ".join(tokens)

    if _contains_any(lowered, joined, ["delete", "remove", "削除", "消して"]):
        return _signal("delete_file", "high", "execute_action", tokens)
    if _contains_any(lowered, joined, ["external", "message", "send", "送信", "外部"]):
        return _signal("send_external_message", "high", "execute_action", tokens)
    if _contains_any(lowered, joined, ["evidence", "source", "prove", "根拠", "証拠"]):
        return _signal("answer_question", "medium", "answer_from_evidence", tokens)
    if _contains_any(lowered, joined, ["rule", "policy", "ルール", "規則"]):
        return _signal("answer_question", "low", "explain_rule", tokens, evidence_present=True)
    if _contains_any(lowered, joined, ["continue", "proceed", "next", "進め", "次"]):
        return _signal("continue_dialogue", "low", "continue_task", tokens, evidence_present=True)
    if len(tokens) <= 1 and len(user_input.strip()) < 12:
        return _signal("unknown", "medium", "clarify_intent", tokens)

    intent = rng.choice(["continue_task", "organize_state", "clarify_intent"])
    risk = "low" if intent != "clarify_intent" else "medium"
    return _signal("continue_dialogue", risk, intent, tokens, evidence_present=True)


def build_action(signal: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_type": signal["action_type"],
        "risk": signal["risk"],
        "approval_present": signal.get("approval_present", False),
        "user_confirmed": signal.get("user_confirmed", False),
        "evidence_present": signal.get("evidence_present", False),
        "log_written": signal.get("log_written", False),
    }


def route_from_policy(policy_result: dict[str, Any], signal: dict[str, Any]) -> str:
    decision = policy_result["decision"]
    if decision == "DENY":
        return "deny"
    if decision == "REQUIRE_EVIDENCE":
        return "require_evidence"
    if decision == "ASK_CONFIRMATION":
        return "ask_confirmation"
    if decision in {"PACK_INVALID", "PACK_NOT_ACTIVE", "CONFLICT", "CLARIFY_RULE"}:
        return "clarify"
    if signal["intent"] == "clarify_intent":
        return "clarify"
    return "continue"


def run_seeded_dialogue_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case in load_jsonl(cases_path):
        result = respond_from_seed(case["input"])
        deterministic = respond_from_seed(case["input"]) == result
        route_ok = result["route"] == case["expected_route"]
        policy_ok = result["policy_decision"] == case["expected_policy_decision"]
        rows.append({
            "case_id": case["case_id"],
            "input": case["input"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "seed": result["seed"],
            "expected_route": case["expected_route"],
            "actual_route": result["route"],
            "expected_policy_decision": case["expected_policy_decision"],
            "actual_policy_decision": result["policy_decision"],
            "route_ok": route_ok,
            "policy_ok": policy_ok,
            "deterministic": deterministic,
            "case_ok": route_ok and policy_ok and deterministic,
            "result": result,
        })
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "route_accuracy": _ratio(row["route_ok"] for row in rows),
        "policy_accuracy": _ratio(row["policy_ok"] for row in rows),
        "determinism_accuracy": _ratio(row["deterministic"] for row in rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "by_tag": _by_tag(rows),
        "claim": "bounded_seeded_dialogue_control_only",
        "blocked_claims": [
            "open_domain_conversation",
            "general_language_understanding",
            "emotional_understanding",
            "llm_quality_parity",
            "transformer_replacement",
        ],
    }
    _write_jsonl(out / "seeded_dialogue_rows.jsonl", rows)
    (out / "seeded_dialogue_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def stable_seed(text: str, salt: str = "lce-seeded-dialogue-v0") -> int:
    digest = hashlib.blake2b(f"{salt}\0{text}".encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _signal(action_type: str, risk: str, intent: str, tokens: list[str], evidence_present: bool = False) -> dict[str, Any]:
    return {
        "action_type": action_type,
        "risk": risk,
        "intent": intent,
        "tokens": tokens,
        "approval_present": False,
        "user_confirmed": False,
        "evidence_present": evidence_present,
        "log_written": False,
    }


def _contains_any(lowered: str, joined_tokens: str, needles: list[str]) -> bool:
    return any(needle in lowered or needle in joined_tokens for needle in needles)


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
