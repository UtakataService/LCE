from lce_validation.runtime.dialogue_resolver import resolve_frame
from lce_validation.runtime.utterance_frame import frame_utterance
from lce_validation.runtime.daily_dialogue import DailyDialogueState, respond_daily_dialogue


def test_frame_tracks_negation_discourse_and_interpersonal_features():
    frame=frame_utterance("Actually, I do not want advice; let us return to the earlier topic.")
    assert frame["polarity"]=="repair"
    assert frame["discourse"]=="return"


def test_resolver_requires_margin_and_state_for_return():
    frame=frame_utterance("let us return to the earlier topic")
    decision=resolve_frame(frame,DailyDialogueState(topic_stack=("opening",)))
    assert decision["decision"]=="SELECT"
    assert decision["act"]=="topic_return"


def test_daily_dialogue_emits_frame_trace_after_card_miss():
    result=respond_daily_dialogue("I feel exhausted and overwhelmed",[])
    assert "utterance_frame" in result
    assert result["route"] in {"daily_dialogue_normalized","daily_dialogue_contextual"}
