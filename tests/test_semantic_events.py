from lce_validation.runtime.conversation_contract import empty_conversation_state
from lce_validation.runtime.conversation_reducer import reduce_turn
from lce_validation.runtime.utterance_frame import frame_utterance


def test_policy_signal_is_a_semantic_event_and_controls_reducer_precedence():
    frame = frame_utterance("My password is abc.")
    assert "sem.policy.privacy" in frame["semantic_ids"]
    assert frame["semantic_events"]["privacy"] is True
    assert reduce_turn(empty_conversation_state(), "My password is abc.")["precedence"] == "privacy"


def test_uptake_signal_is_derived_from_meaning_ids_not_reducer_text_matching():
    first = reduce_turn(empty_conversation_state(), "I am stressed.")
    correction = reduce_turn(first["state"], "Actually, that is not what I meant.")
    assert "sem.uptake.correction" in correction["frame"]["semantic_ids"]
    assert correction["uptake"] == "CORRECTION"
    assert correction["precedence"] == "correction"


def test_trace_records_the_selected_runtime_profile_identity():
    transition = reduce_turn(empty_conversation_state(), "Please just listen.")
    identity = transition["trace"]["payload"]["runtime_profile"]
    assert identity["profile_id"] == "org.lce.reference.frame"
    assert any(ref["pack_id"] == "org.lce.reference.signal.dialogue" for ref in identity["pack_refs"])
