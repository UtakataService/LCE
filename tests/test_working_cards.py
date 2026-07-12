from lce_validation.runtime.working_cards import reconcile_cards
from lce_validation.runtime.daily_dialogue import respond_daily_dialogue


def test_cards_are_bounded_and_deterministic():
    proposed=[("topic",f"topic-{i}","en") for i in range(20)]
    first=reconcile_cards([],proposed,revision=1)
    second=reconcile_cards([],proposed,revision=1)
    assert first==second
    assert len(first)<=3  # Per-kind cap wins before global cap.


def test_sensitive_values_never_become_cards():
    cards=reconcile_cards([],[("constraint","my password is secret","en"),("constraint","PIN 7391","en"),("constraint","private key ABC","en")],revision=1)
    assert cards==()


def test_card_kind_and_value_bounds_are_enforced():
    cards=reconcile_cards([],[("persona","invented","en"),("topic","x"*161,"en")],revision=1)
    assert cards==()


def test_forget_clears_cards():
    cards=reconcile_cards([],[("topic","travel","en")],revision=1)
    assert reconcile_cards(cards,[],revision=2,forget=True)==()


def test_daily_dialogue_exposes_bounded_cards_and_forget():
    first=respond_daily_dialogue("I am tired",[])
    assert first["working_cards"]
    second=respond_daily_dialogue("forget everything",[{"daily_dialogue_state":first["daily_dialogue_state"]}])
    assert second["working_cards"]==()
