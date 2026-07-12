import json
from pathlib import Path

import pytest

from lce_validation.runtime.conversation_contract import (
    ContractError,
    PRECEDENCE,
    SCHEMA_VERSION,
    canonical_json,
    choose_precedence,
    daily_dialogue_compatibility_state,
    empty_conversation_state,
    make_trace_event,
    state_hash,
    validate_conversation_state,
    validate_interpretation,
    validate_replay_fixture,
)
from lce_validation.runtime.daily_dialogue import DailyDialogueState


def _inferred() -> dict:
    return {
        "id": "ih:listen",
        "dimension": "permission",
        "hypothesis": "requests_listening",
        "kind": "inferred",
        "source_turn_hash": "sha256:" + "a" * 64,
        "evidence_spans": [{"start": 0, "end": 8}],
        "confidence": 0.8,
        "status": "TENTATIVE",
    }


def test_empty_state_is_versioned_and_hashable():
    state = empty_conversation_state(session_id="s-1")
    validate_conversation_state(state)
    assert state["schema_version"] == SCHEMA_VERSION
    assert state_hash(state) == state_hash(dict(reversed(list(state.items()))))
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_inference_requires_evidence_and_retracted_items_cannot_be_reused():
    bad = _inferred()
    bad["evidence_spans"] = []
    with pytest.raises(ContractError, match="INFERRED_WITHOUT_EVIDENCE"):
        validate_interpretation(bad)

    state = empty_conversation_state()
    item = _inferred()
    item["status"] = "RETRACTED"
    state["interpretations"] = [item]
    state["repair_ledger"] = [{"reused_interpretation_id": "ih:listen"}]
    with pytest.raises(ContractError, match="RETRACTED_INTERPRETATION_REUSED"):
        validate_conversation_state(state)


@pytest.mark.parametrize("lane", PRECEDENCE)
def test_precedence_table_has_one_contract_per_lane(lane):
    assert choose_precedence({lane: True}) == lane


def test_precedence_is_safety_first_and_rejects_unknown_lanes():
    assert choose_precedence({"response_step": True, "safety": True}) == "safety"
    with pytest.raises(ContractError, match="UNKNOWN_PRECEDENCE_SIGNAL"):
        choose_precedence({"invented": True})


def test_trace_is_redacted_and_deterministic():
    before = empty_conversation_state(session_id="s-1")
    after = empty_conversation_state(session_id="s-1")
    after["revision"] = 1
    after["parent_hash"] = state_hash(before)
    trace = make_trace_event(
        event_id="e-1", state_before=before, state_after=after,
        route="shadow", response_step_kind="clarify", policy_version="p0",
        payload={"email": "user@example.test", "note": "card 4111 1111 1111 1111"},
    )
    assert trace["redaction_count"] == 2
    assert "user@example.test" not in json.dumps(trace)
    assert "4111" not in json.dumps(trace)


def test_legacy_adapter_fails_closed_and_preserves_bounded_safe_fields():
    bad = daily_dialogue_compatibility_state({"revision": "not-a-number"})
    assert bad == empty_conversation_state(session_id="legacy-ephemeral")
    restored = daily_dialogue_compatibility_state(DailyDialogueState(revision=3, topic_stack=("a", "b")))
    assert restored["revision"] == 3
    assert restored["topic_stack"] == ["a", "b"]


def test_exposed_replay_fixture_bank_is_multi_turn_and_contract_valid():
    path = Path("lce_validation/fixtures/conversation_orchestrator_phase0_replay.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= 20
    assert len({row["case_id"] for row in rows}) == len(rows)
    for row in rows:
        validate_replay_fixture(row)
