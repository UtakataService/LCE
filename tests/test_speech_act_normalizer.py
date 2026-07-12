from lce_validation.runtime.daily_dialogue import respond_daily_dialogue
from lce_validation.runtime.speech_act_normalizer import normalize_speech_act


def test_normalizer_uses_multiple_cues():
    assert normalize_speech_act("I feel exhausted and overwhelmed")["act"]=="share_difficulty"
    assert normalize_speech_act("Could you listen without giving advice?")["act"]=="listen_only"
    assert normalize_speech_act("訂正: そういう意味じゃない")["act"]=="self_correction"


def test_daily_dialogue_uses_normalizer_only_after_card_miss():
    result=respond_daily_dialogue("I feel exhausted and overwhelmed",[])
    assert result["route"]=="daily_dialogue_normalized"
    assert result["dialogue_act"]=="share_difficulty"
