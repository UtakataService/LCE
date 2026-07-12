from lce_validation.runtime.daily_dialogue import respond_daily_dialogue
from lce_validation.runtime.foundation_knowledge import answer_foundation


def test_foundation_answers_are_bilingual_and_bounded():
    assert answer_foundation("What is photosynthesis?")["domain"]=="biology"
    assert answer_foundation("光合成とは何？")["language"]=="ja"
    assert answer_foundation("What is the current stock price?") is None


def test_daily_dialogue_bridges_foundation_question():
    result=respond_daily_dialogue("What is an algorithm?",[])
    assert result["dialogue_act"]=="grounded_foundation_answer"
    assert result["knowledge_binding"]["fact_id"]=="fk-computing-algorithm"
