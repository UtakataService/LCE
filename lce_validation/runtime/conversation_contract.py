"""Versioned, deterministic contracts for the ConversationOrchestrator Phase 0.

This module intentionally contains no response generation or state reducer.  It
freezes the data, precedence, trace, and replay-fixture contracts that a later
orchestrator implementation must satisfy.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
import hashlib
import json
import re
from typing import Any, Mapping


SCHEMA_VERSION = "conversation-orchestrator/v1"
MAX_WORKING_CARDS = 12
MAX_INTERPRETATIONS = 12
MAX_PENDING_QUESTIONS = 6
MAX_TOPIC_STACK = 4
MAX_REFERENCES = 6
MAX_KNOWLEDGE_BINDINGS = 8
MAX_REPAIR_LEDGER = 16
MAX_SAFETY_FLAGS = 8

INTERPRETATION_DIMENSIONS = {"content", "interpersonal", "permission", "discourse"}
INTERPRETATION_STATUS = {"TENTATIVE", "CONFIRMED", "RETRACTED"}
INTERPRETATION_KINDS = {"observed", "inferred"}
RESPONSE_STEP_KINDS = {"reflect", "clarify", "offer_choice", "answer", "boundary", "close"}

# Lower index is stronger.  This is a policy contract, not a classifier.
PRECEDENCE = (
    "validation",
    "privacy",
    "safety",
    "deletion",
    "correction",
    "output_contract",
    "frame",
    "interpretation",
    "uptake_repair",
    "knowledge",
    "response_step",
    "render",
    "state_commit",
)

_SENSITIVE_KEYS = {
    "api_key", "authorization", "card_number", "credential", "email",
    "password", "secret", "token",
}
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_CARD = re.compile(r"(?:\d[ -]?){12,16}")


class ContractError(ValueError):
    """Raised when a canonical contract is malformed or unsafe to persist."""


def empty_conversation_state(*, session_id: str = "ephemeral") -> dict[str, Any]:
    """Return the only safe fallback state for malformed legacy history."""
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "revision": 0,
        "parent_hash": None,
        "working_cards": [],
        "utterance_frame": None,
        "interpretations": [],
        "pending_questions": [],
        "topic_stack": [],
        "references": [],
        "knowledge_bindings": [],
        "response_obligation": None,
        "repair_ledger": [],
        "safety_flags": [],
    }


def canonical_json(value: Any) -> str:
    """Serialize only JSON values in a stable form suitable for hashing."""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError("NON_CANONICAL_JSON") from exc


def state_hash(state: Mapping[str, Any]) -> str:
    validate_conversation_state(state)
    return "sha256:" + hashlib.sha256(canonical_json(dict(state)).encode("utf-8")).hexdigest()


def choose_precedence(signals: Mapping[str, bool]) -> str:
    """Choose the first asserted policy lane and reject unknown lane names."""
    unknown = set(signals) - set(PRECEDENCE)
    if unknown:
        raise ContractError(f"UNKNOWN_PRECEDENCE_SIGNAL:{sorted(unknown)[0]}")
    return next((lane for lane in PRECEDENCE if signals.get(lane, False)), "state_commit")


def validate_conversation_state(state: Mapping[str, Any]) -> None:
    if not isinstance(state, Mapping):
        raise ContractError("STATE_NOT_OBJECT")
    required = set(empty_conversation_state())
    missing = required - set(state)
    if missing:
        raise ContractError(f"STATE_MISSING:{sorted(missing)[0]}")
    if state["schema_version"] != SCHEMA_VERSION:
        raise ContractError("SCHEMA_VERSION_MISMATCH")
    if not isinstance(state["session_id"], str) or not state["session_id"]:
        raise ContractError("INVALID_SESSION_ID")
    if not _is_nonnegative_int(state["revision"]):
        raise ContractError("INVALID_REVISION")
    if state["parent_hash"] is not None and not _is_hash(state["parent_hash"]):
        raise ContractError("INVALID_PARENT_HASH")
    _validate_list(state, "working_cards", MAX_WORKING_CARDS)
    _validate_list(state, "interpretations", MAX_INTERPRETATIONS)
    _validate_list(state, "pending_questions", MAX_PENDING_QUESTIONS)
    _validate_list(state, "topic_stack", MAX_TOPIC_STACK)
    _validate_list(state, "references", MAX_REFERENCES)
    _validate_list(state, "knowledge_bindings", MAX_KNOWLEDGE_BINDINGS)
    _validate_list(state, "repair_ledger", MAX_REPAIR_LEDGER)
    _validate_list(state, "safety_flags", MAX_SAFETY_FLAGS)
    if state["utterance_frame"] is not None and not isinstance(state["utterance_frame"], Mapping):
        raise ContractError("INVALID_UTTERANCE_FRAME")
    if state["response_obligation"] is not None and not isinstance(state["response_obligation"], Mapping):
        raise ContractError("INVALID_RESPONSE_OBLIGATION")
    for item in state["interpretations"]:
        validate_interpretation(item)
    retracted = {item["id"] for item in state["interpretations"] if item["status"] == "RETRACTED"}
    reused = {entry.get("reused_interpretation_id") for entry in state["repair_ledger"] if isinstance(entry, Mapping)}
    if retracted & reused:
        raise ContractError("RETRACTED_INTERPRETATION_REUSED")


def validate_interpretation(item: Mapping[str, Any]) -> None:
    required = {"id", "dimension", "hypothesis", "kind", "source_turn_hash", "evidence_spans", "confidence", "status"}
    if not isinstance(item, Mapping) or required - set(item):
        raise ContractError("INVALID_INTERPRETATION")
    if not isinstance(item["id"], str) or not item["id"]:
        raise ContractError("INVALID_INTERPRETATION_ID")
    if item["dimension"] not in INTERPRETATION_DIMENSIONS:
        raise ContractError("INVALID_INTERPRETATION_DIMENSION")
    if item["kind"] not in INTERPRETATION_KINDS:
        raise ContractError("INVALID_INTERPRETATION_KIND")
    if item["status"] not in INTERPRETATION_STATUS:
        raise ContractError("INVALID_INTERPRETATION_STATUS")
    if not isinstance(item["hypothesis"], str) or not item["hypothesis"]:
        raise ContractError("INVALID_HYPOTHESIS")
    if not _is_hash(item["source_turn_hash"]):
        raise ContractError("INVALID_SOURCE_TURN_HASH")
    if not isinstance(item["evidence_spans"], list):
        raise ContractError("INVALID_EVIDENCE_SPANS")
    if item["kind"] == "inferred" and not item["evidence_spans"]:
        raise ContractError("INFERRED_WITHOUT_EVIDENCE")
    if not isinstance(item["confidence"], (int, float)) or isinstance(item["confidence"], bool) or not 0 <= item["confidence"] <= 1:
        raise ContractError("INVALID_CONFIDENCE")


def validate_response_step(step: Mapping[str, Any]) -> None:
    if not isinstance(step, Mapping) or {"kind", "text", "forbidden"} - set(step):
        raise ContractError("INVALID_RESPONSE_STEP")
    if step["kind"] not in RESPONSE_STEP_KINDS or not isinstance(step["text"], str):
        raise ContractError("INVALID_RESPONSE_STEP")
    if not isinstance(step["forbidden"], list) or not all(isinstance(x, str) for x in step["forbidden"]):
        raise ContractError("INVALID_RESPONSE_STEP_FORBIDDEN")


def validate_conversation_plan(plan: Mapping[str, Any]) -> None:
    if not isinstance(plan, Mapping) or {"plan_id", "response_steps", "evidence_refs"} - set(plan):
        raise ContractError("INVALID_CONVERSATION_PLAN")
    if not isinstance(plan["plan_id"], str) or not plan["plan_id"]:
        raise ContractError("INVALID_PLAN_ID")
    if not isinstance(plan["response_steps"], list) or not plan["response_steps"]:
        raise ContractError("EMPTY_RESPONSE_PLAN")
    for step in plan["response_steps"]:
        validate_response_step(step)
    if not isinstance(plan["evidence_refs"], list):
        raise ContractError("INVALID_EVIDENCE_REFS")


def validate_trace_event(event: Mapping[str, Any]) -> None:
    required = {"schema_version", "event_id", "session_id", "route", "response_step_kind", "before_hash", "after_hash", "policy_version", "redaction_count"}
    if not isinstance(event, Mapping) or required - set(event):
        raise ContractError("INVALID_TRACE_EVENT")
    if event["schema_version"] != SCHEMA_VERSION:
        raise ContractError("TRACE_SCHEMA_VERSION_MISMATCH")
    if not all(isinstance(event[key], str) and event[key] for key in ("event_id", "session_id", "route", "response_step_kind", "policy_version")):
        raise ContractError("INVALID_TRACE_IDENTITY")
    if event["response_step_kind"] not in RESPONSE_STEP_KINDS:
        raise ContractError("INVALID_TRACE_STEP")
    if not _is_hash(event["before_hash"]) or not _is_hash(event["after_hash"]):
        raise ContractError("INVALID_TRACE_HASH")
    if not _is_nonnegative_int(event["redaction_count"]):
        raise ContractError("INVALID_REDACTION_COUNT")


def redact_trace_payload(value: Any) -> tuple[Any, int]:
    """Remove common secret forms before a trace is persisted."""
    count = 0

    def visit(item: Any, key: str | None = None) -> Any:
        nonlocal count
        if key and key.casefold() in _SENSITIVE_KEYS:
            count += 1
            return "[REDACTED]"
        if isinstance(item, Mapping):
            return {str(k): visit(v, str(k)) for k, v in item.items()}
        if isinstance(item, list):
            return [visit(v) for v in item]
        if isinstance(item, str):
            redacted = _CARD.sub("[REDACTED]", _EMAIL.sub("[REDACTED]", item))
            if redacted != item:
                count += 1
            return redacted
        return item

    return visit(deepcopy(value)), count


def make_trace_event(*, event_id: str, state_before: Mapping[str, Any], state_after: Mapping[str, Any], route: str, response_step_kind: str, policy_version: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a redacted deterministic event.  Callers own persistence."""
    redacted_payload, redaction_count = redact_trace_payload(dict(payload or {}))
    event = {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "session_id": state_after.get("session_id", state_before.get("session_id")),
        "route": route,
        "response_step_kind": response_step_kind,
        "before_hash": state_hash(state_before),
        "after_hash": state_hash(state_after),
        "policy_version": policy_version,
        "redaction_count": redaction_count,
        "payload": redacted_payload,
    }
    validate_trace_event(event)
    return event


def daily_dialogue_compatibility_state(value: Any, *, session_id: str = "legacy-ephemeral") -> dict[str, Any]:
    """Read legacy state defensively; malformed data never becomes canonical state."""
    if is_dataclass(value):
        value = asdict(value)
    if not isinstance(value, Mapping):
        return empty_conversation_state(session_id=session_id)
    try:
        state = empty_conversation_state(session_id=session_id)
        revision = value.get("revision", 0)
        if not _is_nonnegative_int(revision):
            return state
        state["revision"] = revision
        topic_stack = value.get("topic_stack", ())
        if isinstance(topic_stack, (list, tuple)) and all(isinstance(x, str) for x in topic_stack):
            state["topic_stack"] = list(topic_stack)[-MAX_TOPIC_STACK:]
        cards = value.get("working_cards", ())
        if isinstance(cards, (list, tuple)) and all(isinstance(x, Mapping) for x in cards):
            state["working_cards"] = [dict(x) for x in cards[-MAX_WORKING_CARDS:]]
        validate_conversation_state(state)
        return state
    except (ContractError, TypeError, ValueError):
        return empty_conversation_state(session_id=session_id)


def validate_replay_fixture(row: Mapping[str, Any]) -> None:
    required = {"case_id", "turns", "expected"}
    if not isinstance(row, Mapping) or required - set(row):
        raise ContractError("INVALID_REPLAY_FIXTURE")
    if not isinstance(row["case_id"], str) or not row["case_id"]:
        raise ContractError("INVALID_FIXTURE_ID")
    if not isinstance(row["turns"], list) or len(row["turns"]) < 2:
        raise ContractError("FIXTURE_REQUIRES_MULTI_TURN")
    if not all(isinstance(turn, Mapping) and isinstance(turn.get("text"), str) and turn["text"] for turn in row["turns"]):
        raise ContractError("INVALID_FIXTURE_TURN")
    expected = row["expected"]
    if not isinstance(expected, Mapping) or {"precedence", "response_step", "forbidden"} - set(expected):
        raise ContractError("INVALID_FIXTURE_EXPECTATION")
    if expected["precedence"] not in PRECEDENCE or expected["response_step"] not in RESPONSE_STEP_KINDS:
        raise ContractError("INVALID_FIXTURE_EXPECTATION")
    if not isinstance(expected["forbidden"], list):
        raise ContractError("INVALID_FIXTURE_FORBIDDEN")


def _validate_list(state: Mapping[str, Any], key: str, maximum: int) -> None:
    if not isinstance(state[key], list) or len(state[key]) > maximum:
        raise ContractError(f"INVALID_{key.upper()}")


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))
