from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .rule_composition import compose_rules


SUPPORTED_SCHEMA_VERSION = "policy_pack.v1"
ENGINE_VERSION = "lce-policy-lifecycle-v0"
ACTIVE_STATUSES = {"active"}
KNOWN_STATUSES = {"draft", "active", "retired"}


def validate_policy_pack(policy_pack: dict[str, Any], engine_version: str = ENGINE_VERSION) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    pack_id = policy_pack.get("policy_pack_id")
    if not isinstance(pack_id, str) or not pack_id.strip():
        errors.append("missing_policy_pack_id")

    if policy_pack.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")

    if policy_pack.get("min_engine_version") not in (None, engine_version):
        errors.append("incompatible_engine_version")

    lifecycle_status = policy_pack.get("lifecycle_status")
    if lifecycle_status not in KNOWN_STATUSES:
        errors.append("unknown_lifecycle_status")

    version = policy_pack.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append("missing_version")

    rules = policy_pack.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("missing_rules")
    else:
        seen_rule_ids: set[str] = set()
        for index, rule in enumerate(rules):
            rule_id = rule.get("rule_id")
            if not isinstance(rule_id, str) or not rule_id.strip():
                errors.append(f"missing_rule_id:{index}")
                continue
            if rule_id in seen_rule_ids:
                errors.append(f"duplicate_rule_id:{rule_id}")
            seen_rule_ids.add(rule_id)
            if "rule_text" not in rule:
                errors.append(f"missing_rule_text:{rule_id}")
            if not isinstance(rule.get("priority", 0), int):
                errors.append(f"invalid_priority:{rule_id}")

    if lifecycle_status == "draft":
        warnings.append("draft_policy_pack_cannot_activate")
    if lifecycle_status == "retired":
        warnings.append("retired_policy_pack_cannot_activate")

    return {
        "ok": not errors,
        "policy_pack_id": pack_id,
        "schema_version": policy_pack.get("schema_version"),
        "version": version,
        "lifecycle_status": lifecycle_status,
        "engine_version": engine_version,
        "errors": errors,
        "warnings": warnings,
    }


def activate_policy_pack(policy_pack: dict[str, Any], engine_version: str = ENGINE_VERSION) -> dict[str, Any]:
    validation = validate_policy_pack(policy_pack, engine_version=engine_version)
    if not validation["ok"]:
        return {
            "ok": False,
            "activation_state": "invalid",
            "reason": "policy pack failed validation",
            "validation": validation,
        }
    if validation["lifecycle_status"] not in ACTIVE_STATUSES:
        return {
            "ok": False,
            "activation_state": "not_active",
            "reason": f"policy pack status is {validation['lifecycle_status']}",
            "validation": validation,
        }
    return {
        "ok": True,
        "activation_state": "active",
        "reason": "policy pack is valid and active",
        "validation": validation,
    }


def evaluate_policy_pack(policy_pack: dict[str, Any], action: dict[str, Any], engine_version: str = ENGINE_VERSION) -> dict[str, Any]:
    activation = activate_policy_pack(policy_pack, engine_version=engine_version)
    pack_id = policy_pack.get("policy_pack_id")
    if not activation["ok"]:
        decision = "PACK_INVALID" if activation["activation_state"] == "invalid" else "PACK_NOT_ACTIVE"
        return {
            "ok": True,
            "policy_pack_id": pack_id,
            "decision": decision,
            "winning_rule_id": None,
            "reason": activation["reason"],
            "activation": activation,
            "trace": [
                f"pack:{pack_id}",
                f"activation:{activation['activation_state']}",
                f"decision:{decision}",
            ],
            "claim": "bounded_policy_pack_lifecycle_only",
            "blocked_claims": _blocked_claims(policy_pack),
        }

    composition = compose_rules(policy_pack["rules"], action, policy_pack.get("default_policy", "ALLOW"))
    return {
        "ok": True,
        "policy_pack_id": pack_id,
        "decision": composition["decision"],
        "winning_rule_id": composition.get("winning_rule_id"),
        "reason": composition["reason"],
        "activation": activation,
        "composition": composition,
        "trace": [
            f"pack:{pack_id}",
            f"version:{policy_pack.get('version')}",
            "activation:active",
            f"decision:{composition['decision']}",
        ],
        "claim": "bounded_policy_pack_lifecycle_only",
        "blocked_claims": _blocked_claims(policy_pack),
    }


def run_policy_pack_lifecycle_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case in load_jsonl(cases_path):
        result = evaluate_policy_pack(case["policy_pack"], case["action"])
        decision_ok = result["decision"] == case["expected_decision"]
        activation_ok = result["activation"]["activation_state"] == case["expected_activation_state"]
        winner_ok = result.get("winning_rule_id") == case.get("expected_winning_rule_id")
        rows.append({
            "case_id": case["case_id"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "expected_decision": case["expected_decision"],
            "actual_decision": result["decision"],
            "expected_activation_state": case["expected_activation_state"],
            "actual_activation_state": result["activation"]["activation_state"],
            "expected_winning_rule_id": case.get("expected_winning_rule_id"),
            "actual_winning_rule_id": result.get("winning_rule_id"),
            "decision_ok": decision_ok,
            "activation_ok": activation_ok,
            "winner_ok": winner_ok,
            "case_ok": decision_ok and activation_ok and winner_ok,
            "result": result,
        })
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "decision_accuracy": _ratio(row["decision_ok"] for row in rows),
        "activation_accuracy": _ratio(row["activation_ok"] for row in rows),
        "winner_accuracy": _ratio(row["winner_ok"] for row in rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "by_tag": _by_tag(rows),
        "claim": "bounded_policy_pack_lifecycle_only",
        "blocked_claims": [
            "open_domain_conversation",
            "general_language_understanding",
            "legal_policy_reasoning",
            "production_policy_governance",
            "transformer_replacement",
        ],
    }
    _write_jsonl(out / "policy_pack_lifecycle_rows.jsonl", rows)
    (out / "policy_pack_lifecycle_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _blocked_claims(policy_pack: dict[str, Any]) -> list[str]:
    claims = policy_pack.get("blocked_claims")
    if isinstance(claims, list) and all(isinstance(item, str) for item in claims):
        return claims
    return [
        "open_domain_conversation",
        "general_language_understanding",
        "production_policy_governance",
        "transformer_replacement",
    ]


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
