import json
from pathlib import Path

import pytest

from lce_validation.runtime.conversation_contract import ContractError, empty_conversation_state, state_hash
from lce_validation.runtime.conversation_reducer import adapt_utterance_frame, reduce_turn, replay_fixture, replay_turns
from lce_validation.runtime.utterance_frame import frame_utterance, frame_utterance_legacy


def test_reducer_is_pure_and_replay_is_deterministic():
    state = empty_conversation_state(session_id="pure")
    before_hash = state_hash(state)
    first = reduce_turn(state, "I had a rough day. Please just listen for now.")
    second = reduce_turn(state, "I had a rough day. Please just listen for now.")
    assert state_hash(state) == before_hash
    assert first["state"] == second["state"]
    assert first["trace"] == second["trace"]
    assert first["plan"]["response_steps"][0]["kind"] == "reflect"


def test_correction_retracts_prior_tentative_interpretations_without_reuse():
    first = reduce_turn(empty_conversation_state(), "I am stressed.")
    corrected = reduce_turn(first["state"], "Actually, that is not what I meant.")
    assert corrected["precedence"] == "correction"
    assert any(item["status"] == "RETRACTED" for item in corrected["state"]["interpretations"])
    assert corrected["plan"]["response_steps"][0]["forbidden"] == ["stale_interpretation_reuse"]


def test_forget_is_ephemeral_and_clears_only_bounded_session_context():
    state = empty_conversation_state()
    state["working_cards"] = [{"id": "card-1"}]
    state["references"] = [{"id": "ref-1"}]
    transition = reduce_turn(state, "Forget that preference.")
    assert transition["precedence"] == "deletion"
    assert transition["state"]["working_cards"] == []
    assert all(item["status"] == "RETRACTED" for item in transition["state"]["interpretations"])
    assert transition["state"]["safety_flags"] == ["persistent_deletion_not_claimed"]


def test_output_contract_suppresses_semantic_hypotheses_and_keeps_them_out_of_plan():
    first = reduce_turn(empty_conversation_state(), "Summarize this task.")
    structured = reduce_turn(first["state"], "Return only JSON with status.")
    assert structured["precedence"] == "output_contract"
    assert structured["state"]["interpretations"] == first["state"]["interpretations"]
    assert structured["plan"]["selected_interpretation_ids"] == []


def test_low_support_reference_is_withheld_and_drives_unknown_clarification():
    first = reduce_turn(empty_conversation_state(), "I saw something unusual.")
    reference = reduce_turn(first["state"], "Do that again.")
    assert reference["precedence"] == "interpretation"
    assert reference["plan"]["selected_interpretation_ids"] == []
    assert reference["plan"]["withheld_interpretation_ids"]
    assert reference["plan"]["response_steps"][0]["kind"] == "clarify"


def test_reducer_rejects_invalid_canonical_state():
    invalid = empty_conversation_state()
    invalid["schema_version"] = "old"
    with pytest.raises(ContractError, match="SCHEMA_VERSION_MISMATCH"):
        reduce_turn(invalid, "hello")


def test_all_phase0_exposed_fixtures_replay_to_their_contract():
    path = Path("lce_validation/fixtures/conversation_orchestrator_phase0_replay.jsonl")
    fixtures = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    outcomes = [replay_fixture(fixture) for fixture in fixtures]
    assert all(item["passed"] for item in outcomes), [item["case_id"] for item in outcomes if not item["passed"]]


def test_replay_records_do_not_store_raw_turn_text_and_match_exactly():
    turns = [{"text": "I am tired."}, {"text": "Please just listen."}]
    one = replay_turns(turns, session_id="stable")
    two = replay_turns(turns, session_id="stable")
    assert one == two
    assert "I am tired" not in json.dumps(one)


def test_reducer_projects_canonical_utterance_frame_to_its_bounded_cue_contract():
    canonical = frame_utterance("Please offer a few ideas.")
    projected = adapt_utterance_frame(canonical)
    assert projected["language"] == "en"
    assert projected["cues"] == ["advice_permitted"]
    assert projected["runtime_profile"]["profile_lock_hash"].startswith("sha256:")


def test_compatibility_aliases_keep_pack_and_legacy_frame_paths_in_lockstep():
    for text in ("Please offer a few ideas.", "I had a rough day.", "\u9078\u629e\u80a2\u3092\u63d0\u6848\u3057\u3066\u3002"):
        assert frame_utterance(text) == frame_utterance_legacy(text)
