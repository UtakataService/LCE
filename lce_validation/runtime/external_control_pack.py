"""Data-defined LCE control planning for external LLM and retrieval adapters."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Mapping

from .model_pack import PackValidationError, canonical_json, content_hash, validate_pack


class ControlPackError(ValueError):
    pass


def validate_control_pack(pack: Mapping[str, Any]) -> None:
    validate_pack(pack)
    if pack.get("pack_type") != "ControlPack":
        raise ControlPackError("NOT_CONTROL_PACK")
    payload = pack["payload"]
    required = {"default_intent_id", "retrieval_threshold", "intents", "models", "actions"}
    if required - set(payload) or not 0 <= payload["retrieval_threshold"] <= 1:
        raise ControlPackError("INVALID_CONTROL_PAYLOAD")
    if not isinstance(payload["intents"], list) or not isinstance(payload["models"], list) or not isinstance(payload["actions"], list):
        raise ControlPackError("INVALID_CONTROL_PAYLOAD")
    intent_ids = set()
    for intent in payload["intents"]:
        fields = {"intent_id", "priority", "signals", "retrieval_policy", "context_strategy", "model_classes"}
        if not isinstance(intent, Mapping) or fields - set(intent) or intent["intent_id"] in intent_ids:
            raise ControlPackError("INVALID_CONTROL_INTENT")
        if intent["retrieval_policy"] not in {"never", "always", "when_unknown"} or intent["context_strategy"] not in {"recent", "important"}:
            raise ControlPackError("INVALID_CONTROL_INTENT")
        if not isinstance(intent["priority"], int) or not isinstance(intent["signals"], Mapping) or not isinstance(intent["model_classes"], list):
            raise ControlPackError("INVALID_CONTROL_INTENT")
        intent_ids.add(intent["intent_id"])
    if payload["default_intent_id"] not in intent_ids:
        raise ControlPackError("DEFAULT_INTENT_NOT_DECLARED")
    for model in payload["models"]:
        if not isinstance(model, Mapping) or {"model_id", "classes", "enabled"} - set(model) or not isinstance(model["classes"], list):
            raise ControlPackError("INVALID_CONTROL_MODEL")
    action_ids = set()
    for action in payload["actions"]:
        fields = {"action_id", "status", "operation", "allowed_intent_ids", "decision_rule"}
        if not isinstance(action, Mapping) or fields - set(action) or action["action_id"] in action_ids:
            raise ControlPackError("INVALID_CONTROL_ACTION")
        if action["operation"] not in {"adapter", "status"} or not set(action["allowed_intent_ids"]).issubset(intent_ids):
            raise ControlPackError("INVALID_CONTROL_ACTION")
        rule = action["decision_rule"]
        if not isinstance(rule, Mapping) or rule.get("mode") not in {"always", "when_unknown", "when_signaled"}:
            raise ControlPackError("INVALID_CONTROL_ACTION")
        action_ids.add(action["action_id"])


def plan_external_request(request: Mapping[str, Any], pack: Mapping[str, Any]) -> dict[str, Any]:
    """Produce an auditable plan. It does not execute adapters or commit state."""
    validate_control_pack(pack)
    if not isinstance(request, Mapping) or not isinstance(request.get("text"), str):
        raise ControlPackError("INVALID_CONTROL_REQUEST")
    payload, text = pack["payload"], request["text"].casefold()
    matches = [item for item in payload["intents"] if _matches(text, item["signals"])]
    intent = sorted(matches or [next(item for item in payload["intents"] if item["intent_id"] == payload["default_intent_id"])], key=lambda item: (-item["priority"], item["intent_id"]))[0]
    confidence = float(request.get("knowledge_confidence", 0.0))
    retrieval = "RETRIEVE" if intent["retrieval_policy"] == "always" or (intent["retrieval_policy"] == "when_unknown" and confidence < payload["retrieval_threshold"]) else "SKIP"
    model = _select_model(intent, payload["models"])
    history = request.get("history", [])
    context = _select_context(history, intent["context_strategy"], int(request.get("max_context_items", 3)))
    actions = _select_actions(intent, payload["actions"], text, confidence, payload["retrieval_threshold"])
    status = "READY" if model else "NO_ELIGIBLE_MODEL"
    return {"status": status, "intent_id": intent["intent_id"], "request_kind": intent.get("request_kind", intent["intent_id"]), "retrieval": {"action": retrieval, "reason": intent["retrieval_policy"]}, "actions": actions, "context": context, "model": model, "trace": {"pack_id": pack["pack_id"], "pack_hash": pack["content_hash"], "matched_intent_ids": [item["intent_id"] for item in matches]}}


def build_router_instruction(request: Mapping[str, Any], pack: Mapping[str, Any]) -> str:
    """Optional LLM-router prompt. Its JSON remains a candidate, never authority."""
    validate_control_pack(pack)
    payload = pack["payload"]
    allowed = {"intent_ids": [row["intent_id"] for row in payload["intents"]], "model_ids": [row["model_id"] for row in payload["models"]], "retrieval_actions": ["RETRIEVE", "SKIP"]}
    return "Return JSON only with intent_id, model_id, retrieval_action. Choose only allowed values; do not execute.\n" + f"ALLOWED={json.dumps(allowed, sort_keys=True)}\nUSER_INPUT={request.get('text', '')}"


def validate_router_candidate(candidate: Mapping[str, Any], pack: Mapping[str, Any]) -> dict[str, Any]:
    """Accept a router-LLM proposal only when it is permitted by the ControlPack."""
    validate_control_pack(pack)
    if not isinstance(candidate, Mapping) or {"intent_id", "model_id", "retrieval_action"} - set(candidate):
        return {"accepted": False, "reason": "INVALID_ROUTER_CANDIDATE"}
    payload = pack["payload"]
    intent = next((row for row in payload["intents"] if row["intent_id"] == candidate["intent_id"]), None)
    model = next((row for row in payload["models"] if row["model_id"] == candidate["model_id"]), None)
    if intent is None or model is None or not model["enabled"] or not set(intent["model_classes"]) & set(model["classes"]):
        return {"accepted": False, "reason": "ROUTER_CANDIDATE_NOT_ALLOWED"}
    if candidate["retrieval_action"] not in {"RETRIEVE", "SKIP"} or (intent["retrieval_policy"] == "never" and candidate["retrieval_action"] == "RETRIEVE"):
        return {"accepted": False, "reason": "ROUTER_RETRIEVAL_NOT_ALLOWED"}
    return {"accepted": True, "candidate": {"intent_id": intent["intent_id"], "model_id": model["model_id"], "retrieval_action": candidate["retrieval_action"]}}


def execute_external_plan(plan: Mapping[str, Any], request: Mapping[str, Any], *, model_invoke: Callable[[str, str, list[dict[str, Any]], list[dict[str, Any]]], Any], retrieve: Callable[[str], list[dict[str, Any]]] | None = None, action_adapters: Mapping[str, Callable[[str], Any]] | None = None) -> dict[str, Any]:
    """Execute only the already-approved model/retrieval plan through supplied adapters."""
    if plan.get("status") != "READY" or not isinstance(plan.get("model"), Mapping):
        return {"status": "BLOCKED", "reason": "PLAN_NOT_READY"}
    if plan["retrieval"]["action"] == "RETRIEVE":
        if retrieve is None: return {"status": "BLOCKED", "reason": "RETRIEVER_UNAVAILABLE"}
        retrieved = retrieve(str(request["text"]))
    else: retrieved = []
    action_results = []
    for action in plan.get("actions", []):
        if action["operation"] == "status":
            action_results.append({"action_id": action["action_id"], "status": action["status"]})
            continue
        adapter = (action_adapters or {}).get(action["action_id"])
        if adapter is None: return {"status": "BLOCKED", "reason": "ACTION_ADAPTER_UNAVAILABLE", "action_id": action["action_id"]}
        action_results.append({"action_id": action["action_id"], "status": action["status"], "result": adapter(str(request["text"]))})
    response = model_invoke(str(plan["model"]["model_id"]), str(request["text"]), list(plan["context"]), retrieved + action_results)
    return {"status": "EXECUTED", "model_id": plan["model"]["model_id"], "response": response, "retrieval_count": len(retrieved), "action_count": len(action_results)}


def _matches(text: str, signals: Mapping[str, Any]) -> bool:
    any_terms = [str(x).casefold() for x in signals.get("any_terms", [])]
    all_terms = [str(x).casefold() for x in signals.get("all_terms", [])]
    return (not any_terms or any(term in text for term in any_terms)) and all(term in text for term in all_terms)


def _select_model(intent: Mapping[str, Any], models: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    for preferred in intent["model_classes"]:
        for model in models:
            if model["enabled"] and preferred in model["classes"]:
                return {"model_id": model["model_id"], "selected_class": preferred}
    return None


def _select_context(history: Any, strategy: str, limit: int) -> list[dict[str, Any]]:
    rows = [dict(row) for row in history if isinstance(row, Mapping)] if isinstance(history, list) else []
    if strategy == "important": rows.sort(key=lambda row: (-float(row.get("importance", 0)), str(row.get("id", ""))))
    return rows[-limit:] if strategy == "recent" else rows[:limit]


def _select_actions(intent: Mapping[str, Any], actions: list[Mapping[str, Any]], text: str, confidence: float, threshold: float) -> list[dict[str, Any]]:
    selected = []
    for action in actions:
        if intent["intent_id"] not in action["allowed_intent_ids"]: continue
        rule = action["decision_rule"]
        mode = rule["mode"]
        eligible = mode == "always" or (mode == "when_unknown" and confidence < threshold) or (mode == "when_signaled" and _matches(text, rule))
        if eligible:
            selected.append({"action_id": action["action_id"], "status": action["status"], "operation": action["operation"], "criteria": rule.get("criteria", "")})
    return selected
