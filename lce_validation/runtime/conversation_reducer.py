"""Pure, bounded ConversationOrchestrator reducer for Phase 1 shadow replay."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any, Mapping

from .conversation_contract import (
    ContractError,
    MAX_INTERPRETATIONS,
    MAX_REPAIR_LEDGER,
    MAX_TOPIC_STACK,
    RESPONSE_STEP_KINDS,
    canonical_json,
    choose_precedence,
    empty_conversation_state,
    make_trace_event,
    state_hash,
    validate_conversation_plan,
    validate_conversation_state,
)
from .conversation_hypothesis_gate import assess_hypotheses, selected_interpretation_ids, withheld_interpretation_ids
from .flexible_response_envelope import build_flexible_response_envelope, validate_flexible_response_envelope
from .utterance_frame import frame_utterance
from .runtime_profile import RuntimeProfile


POLICY_VERSION = "conversation-orchestrator-phase1"


_CONVERSATION_SEMANTIC_ADAPTER = {
    "sem.interaction.listen_only": "listen_only",
    "sem.interaction.advice_permitted": "advice_permitted",
    "sem.affect.difficulty": "reports_difficulty",
}


def reduce_turn(state: Mapping[str, Any], text: str, *, policy_version: str = POLICY_VERSION, runtime_profile: RuntimeProfile | None = None) -> dict[str, Any]:
    """Return a deterministic transition without persistence, network, or rendering side effects."""
    validate_conversation_state(state)
    if not isinstance(text, str):
        raise ContractError("INPUT_NOT_TEXT")
    before = deepcopy(dict(state))
    after = deepcopy(before)
    turn_hash = _turn_hash(before, text)
    frame = adapt_utterance_frame(frame_utterance(text, runtime_profile=runtime_profile))
    uptake = _uptake(frame, before)
    signals = _signals(text, frame, uptake, before)
    precedence = choose_precedence(signals)
    after["revision"] += 1
    after["parent_hash"] = state_hash(before)
    after["utterance_frame"] = frame

    if precedence == "privacy":
        after["safety_flags"] = ["privacy_sensitive_input"]
    elif precedence == "correction":
        _apply_correction(after, turn_hash)
    elif precedence == "deletion":
        _apply_session_forget(after, turn_hash)

    proposed = _interpretations(text, turn_hash, precedence, frame)
    after["interpretations"] = _bounded_interpretations(after["interpretations"], proposed)
    if uptake in {"SHIFT", "RETURN"}:
        _update_topics(after, uptake)

    assessments = assess_hypotheses(after["interpretations"])
    selected_ids = selected_interpretation_ids(assessments)
    step = _response_step(precedence, frame, uptake, has_decision_support=bool(selected_ids))
    envelope = build_flexible_response_envelope(precedence=precedence, frame=frame, assessments=assessments, response_step=step["kind"])
    validate_flexible_response_envelope(envelope)
    plan = {
        "plan_id": "plan:" + _short_hash({"turn": turn_hash, "precedence": precedence, "step": step["kind"]}),
        "response_steps": [step],
        "evidence_refs": [],
        "selected_interpretation_ids": selected_ids,
        "withheld_interpretation_ids": withheld_interpretation_ids(assessments),
        "flexible_response_envelope": envelope,
    }
    validate_conversation_plan(plan)
    validate_conversation_state(after)
    event = make_trace_event(
        event_id="evt:" + _short_hash({"before": state_hash(before), "turn": turn_hash}),
        state_before=before,
        state_after=after,
        route="conversation_orchestrator_shadow",
        response_step_kind=step["kind"],
        policy_version=policy_version,
        payload={"turn_hash": turn_hash, "precedence": precedence, "uptake": uptake, "fre_mode": envelope["mode"], "fre_risk": envelope["risk_class"], "runtime_profile": frame.get("runtime_profile", {})},
    )
    return {
        "state": after,
        "plan": plan,
        "trace": event,
        "frame": frame,
        "uptake": uptake,
        "precedence": precedence,
        "turn_hash": turn_hash,
        "hypothesis_assessments": assessments,
        "flexible_response_envelope": envelope,
    }


def replay_turns(turns: list[Mapping[str, Any]], *, session_id: str = "replay") -> dict[str, Any]:
    """Replay an exposed episode with a fresh ephemeral state and no I/O."""
    if not isinstance(turns, list) or not turns:
        raise ContractError("EMPTY_REPLAY")
    state = empty_conversation_state(session_id=session_id)
    records: list[dict[str, Any]] = []
    for index, turn in enumerate(turns):
        if not isinstance(turn, Mapping) or not isinstance(turn.get("text"), str) or not turn["text"]:
            raise ContractError(f"INVALID_REPLAY_TURN:{index}")
        transition = reduce_turn(state, turn["text"])
        records.append({
            "turn_index": index,
            "turn_hash": transition["turn_hash"],
            "precedence": transition["precedence"],
            "uptake": transition["uptake"],
            "response_step": transition["plan"]["response_steps"][0]["kind"],
            "forbidden": transition["plan"]["response_steps"][0]["forbidden"],
            "fre_mode": transition["flexible_response_envelope"]["mode"],
            "revision": transition["state"]["revision"],
            "parent_hash": transition["state"]["parent_hash"],
            "state_hash": state_hash(transition["state"]),
            "trace": transition["trace"],
        })
        state = transition["state"]
    return {"state": state, "state_hash": state_hash(state), "records": records}


def replay_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Run one Phase 0 fixture and compare its terminal contract expectations."""
    if not isinstance(fixture, Mapping) or not isinstance(fixture.get("turns"), list):
        raise ContractError("INVALID_REPLAY_FIXTURE")
    result = replay_turns(fixture["turns"], session_id="fixture:" + str(fixture.get("case_id", "unknown")))
    expected = fixture.get("expected", {})
    final = result["records"][-1]
    forbidden = set(expected.get("forbidden", []))
    selected_forbidden = set(final["forbidden"])
    return {
        "case_id": fixture.get("case_id"),
        "result": result,
        "passed": final["precedence"] == expected.get("precedence")
        and final["response_step"] == expected.get("response_step")
        and forbidden <= selected_forbidden,
    }


def _legacy_signals(text: str, frame: Mapping[str, Any], uptake: str, state: Mapping[str, Any]) -> dict[str, bool]:
    lowered = text.casefold()
    direct_privacy = any(token in lowered for token in ("password", "api key", "credit card", "パスワード", "暗証番号"))
    contextual_repeat = "privacy_sensitive_input" in state["safety_flags"] and any(token in lowered for token in ("repeat", "そのまま表示", "もう一度表示"))
    return {
        "validation": not text.strip(),
        "privacy": direct_privacy or contextual_repeat,
        "safety": any(token in lowered for token in ("only real friend", "only support", "君だけに相談", "自分を傷つけ", "suicide")),
        "deletion": any(token in lowered for token in ("forget ", "forget that", "delete my", "忘れて", "削除して")),
        "correction": uptake == "CORRECTION",
        "output_contract": any(token in lowered for token in ("only json", "return json", "jsonで返", "jsonだけ")),
        "frame": bool(frame["cues"]),
        "interpretation": any(token in lowered for token in ("do that again", "それをまた", "that again")),
        "uptake_repair": uptake in {"ACCEPT", "SHIFT", "RETURN"},
        "knowledge": text.strip().endswith(("?", "？")),
        "response_step": True,
    }


def _signals(text: str, frame: Mapping[str, Any], uptake: str, state: Mapping[str, Any]) -> dict[str, bool]:
    events = frame["semantic_events"]
    contextual_repeat = "privacy_sensitive_input" in state["safety_flags"] and bool(events["interpretation"])
    return {
        "validation": not text.strip(),
        "privacy": bool(events["privacy"]) or contextual_repeat,
        "safety": bool(events["safety"]),
        "deletion": bool(events["deletion"]),
        "correction": uptake == "CORRECTION",
        "output_contract": bool(events["output_contract"]),
        "frame": bool(frame["cues"]),
        "interpretation": bool(events["interpretation"]),
        "uptake_repair": uptake in {"ACCEPT", "SHIFT", "RETURN"},
        "knowledge": bool(events["knowledge"]),
        "response_step": True,
    }


def adapt_utterance_frame(frame: Mapping[str, Any]) -> dict[str, Any]:
    """Project the canonical frame onto the bounded reducer cue contract."""
    language = frame.get("language")
    raw_semantic_ids = frame.get("semantic_ids")
    if not isinstance(language, str) or not isinstance(raw_semantic_ids, (list, tuple)):
        raise ContractError("INVALID_UTTERANCE_FRAME")
    cues: list[str] = []
    for semantic_id in raw_semantic_ids:
        mapped = _CONVERSATION_SEMANTIC_ADAPTER.get(semantic_id)
        if mapped is not None and mapped not in cues:
            cues.append(mapped)
    runtime_identity = frame.get("runtime_profile")
    events = frame.get("semantic_events")
    if not isinstance(runtime_identity, Mapping) or not isinstance(events, Mapping):
        raise ContractError("MISSING_RUNTIME_PROFILE")
    return {"language": language, "cues": cues, "semantic_ids": list(raw_semantic_ids), "runtime_profile": dict(runtime_identity), "semantic_events": dict(events)}


def _legacy_uptake(text: str, state: Mapping[str, Any]) -> str:
    if not state["interpretations"]:
        return "INITIAL"
    lowered = text.casefold()
    if any(token in lowered for token in ("actually", "not what i meant", "違う", "そういう意味ではない", "訂正")):
        return "CORRECTION"
    if any(token in lowered for token in ("by the way", "another topic", "ところで", "別の話")):
        return "SHIFT"
    if any(token in lowered for token in ("back to", "earlier plan", "戻ると", "さっきの件")):
        return "RETURN"
    if lowered.strip() in {"yes", "yeah", "exactly", "うん", "そう"}:
        return "ACCEPT"
    return "UNRESOLVED"


def _uptake(frame: Mapping[str, Any], state: Mapping[str, Any]) -> str:
    if not state["interpretations"]:
        return "INITIAL"
    uptake = frame["semantic_events"]["uptake"]
    return uptake if uptake != "INITIAL" else "UNRESOLVED"


def _apply_correction(state: dict[str, Any], turn_hash: str) -> None:
    targets = [item["id"] for item in state["interpretations"] if item["status"] == "TENTATIVE"]
    for item in state["interpretations"]:
        if item["id"] in targets:
            item["status"] = "RETRACTED"
    state["repair_ledger"] = (state["repair_ledger"] + [{
        "event": "retract_tentative", "target_ids": targets, "turn_hash": turn_hash,
    }])[-MAX_REPAIR_LEDGER:]


def _apply_session_forget(state: dict[str, Any], turn_hash: str) -> None:
    state["working_cards"] = []
    state["pending_questions"] = []
    state["topic_stack"] = []
    state["references"] = []
    state["knowledge_bindings"] = []
    state["response_obligation"] = None
    retracted_ids = []
    for item in state["interpretations"]:
        if item["status"] != "RETRACTED":
            item["status"] = "RETRACTED"
            retracted_ids.append(item["id"])
    state["repair_ledger"] = (state["repair_ledger"] + [{
        "event": "session_forget_requested", "scope": "ephemeral_only", "target_ids": retracted_ids, "turn_hash": turn_hash,
    }])[-MAX_REPAIR_LEDGER:]
    state["safety_flags"] = ["persistent_deletion_not_claimed"]


def _legacy_interpretations(text: str, turn_hash: str, precedence: str) -> list[dict[str, Any]]:
    if precedence in {"privacy", "safety", "deletion", "validation", "output_contract"}:
        return []
    lowered = text.casefold()
    candidates: list[tuple[str, str, str, float]] = []
    if any(token in lowered for token in ("just listen", "hear me out", "聞いてほしい", "愚痴")):
        candidates.append(("permission", "requests_listening", "inferred", 0.9))
    if any(token in lowered for token in ("rough day", "stressed", "tired", "疲れ", "困って")):
        candidates.append(("content", "reports_difficulty", "inferred", 0.6))
    if precedence == "correction":
        candidates.append(("discourse", "corrects_prior_interpretation", "observed", 0.9))
    if precedence == "interpretation":
        candidates.append(("discourse", "reference_unclear", "inferred", 0.3))
    if not candidates:
        candidates.append(("content", "meaning_unresolved", "inferred", 0.2))
    return [{
        "id": "ih:" + _short_hash({"turn": turn_hash, "dimension": dimension, "hypothesis": hypothesis}),
        "dimension": dimension,
        "hypothesis": hypothesis,
        "kind": kind,
        "source_turn_hash": turn_hash,
        "evidence_spans": [{"start": 0, "end": len(text)}],
        "confidence": confidence,
        "status": "TENTATIVE",
    } for dimension, hypothesis, kind, confidence in candidates]


def _interpretations(text: str, turn_hash: str, precedence: str, frame: Mapping[str, Any]) -> list[dict[str, Any]]:
    if precedence in {"privacy", "safety", "deletion", "validation", "output_contract"}:
        return []
    semantic_ids = set(frame["semantic_ids"])
    candidates: list[tuple[str, str, str, float]] = []
    if "sem.interaction.listen_only" in semantic_ids:
        candidates.append(("permission", "requests_listening", "inferred", 0.9))
    if "sem.affect.difficulty" in semantic_ids:
        candidates.append(("content", "reports_difficulty", "inferred", 0.6))
    if precedence == "correction":
        candidates.append(("discourse", "corrects_prior_interpretation", "observed", 0.9))
    if precedence == "interpretation":
        candidates.append(("discourse", "reference_unclear", "inferred", 0.3))
    if not candidates:
        candidates.append(("content", "meaning_unresolved", "inferred", 0.2))
    return [{
        "id": "ih:" + _short_hash({"turn": turn_hash, "dimension": dimension, "hypothesis": hypothesis}),
        "dimension": dimension,
        "hypothesis": hypothesis,
        "kind": kind,
        "source_turn_hash": turn_hash,
        "evidence_spans": [{"start": 0, "end": len(text)}],
        "confidence": confidence,
        "status": "TENTATIVE",
    } for dimension, hypothesis, kind, confidence in candidates]


def _bounded_interpretations(existing: list[dict[str, Any]], proposed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = existing + proposed
    # Preserve retractions as long as possible, but never allow state to grow without bound.
    return merged[-MAX_INTERPRETATIONS:]


def _update_topics(state: dict[str, Any], uptake: str) -> None:
    marker = "topic_shift" if uptake == "SHIFT" else "topic_return"
    state["topic_stack"] = (state["topic_stack"] + [marker])[-MAX_TOPIC_STACK:]


def _response_step(precedence: str, frame: Mapping[str, Any], uptake: str, *, has_decision_support: bool) -> dict[str, Any]:
    templates = {
        "validation": ("clarify", "I need a non-empty message before I can continue."),
        "privacy": ("boundary", "Please do not share or repeat sensitive credentials or personal data here."),
        "safety": ("boundary", "I can talk with you, while keeping support beyond this chat in view."),
        "deletion": ("boundary", "I cleared the bounded session context; this does not claim deletion from any external store."),
        "correction": ("clarify", "Thanks for the correction. I have withdrawn the earlier tentative interpretation."),
        "output_contract": ("answer", '{"status":"bounded"}'),
        "interpretation": ("clarify", "I am not sure what that reference points to. Could you name it again?"),
        "uptake_repair": ("clarify", "Okay. Which part should we focus on now?"),
        "knowledge": ("clarify", "I need a bounded evidence source or more context before answering that."),
    }
    if precedence in {"interpretation", "knowledge"} and not has_decision_support:
        kind, text = "clarify", "I do not have enough grounded information to use that as a decision premise. Could you add the missing detail?"
    elif precedence in templates:
        kind, text = templates[precedence]
    elif "listen_only" in frame["cues"]:
        kind, text = "reflect", "I will stay with what you are saying before offering solutions."
    elif "advice_permitted" in frame["cues"]:
        kind, text = "offer_choice", "I can offer a few options while leaving the decision with you."
    elif "reports_difficulty" in frame["cues"]:
        kind, text = "reflect", "That sounds difficult."
    else:
        kind, text = "clarify", "Could you say a little more about what you want from this turn?"
    assert kind in RESPONSE_STEP_KINDS
    return {"kind": kind, "text": text, "forbidden": _forbidden(precedence, uptake, frame)}


def _forbidden(precedence: str, uptake: str, frame: Mapping[str, Any]) -> list[str]:
    mapping = {
        "privacy": ["repeat_sensitive_data"],
        "safety": ["exclusive_relationship"],
        "deletion": ["deleted_fact_reuse"],
        "correction": ["stale_interpretation_reuse"],
        "output_contract": ["non_json_output"],
        "interpretation": ["unsupported_reference"],
        "uptake_repair": ["solve_old_topic", "invented_reference"],
    }
    if precedence == "frame" and "listen_only" in frame["cues"]:
        return ["unwanted_advice"]
    if precedence == "frame" and "advice_permitted" in frame["cues"]:
        return ["directive_decision"]
    return mapping.get(precedence, [])


def _turn_hash(state: Mapping[str, Any], text: str) -> str:
    return "sha256:" + hashlib.sha256(canonical_json({"session": state["session_id"], "revision": state["revision"] + 1, "text": text}).encode("utf-8")).hexdigest()


def _short_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(dict(value)).encode("utf-8")).hexdigest()[:16]
