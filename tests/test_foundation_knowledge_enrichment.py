import json
from pathlib import Path

from lce_validation.runtime.foundation_knowledge import FOUNDATION_DATA_PATH, answer_foundation, load_foundation_facts


BENCHMARK_PATH = Path("lce_validation/fixtures/foundation_knowledge_enrichment_benchmark_v1.jsonl")


def test_foundation_pack_is_data_driven_and_has_all_ten_categories():
    facts = load_foundation_facts()
    assert FOUNDATION_DATA_PATH.exists()
    assert len(facts) >= 50
    assert {fact["category"] for fact in facts} == {
        "01_math_quantities", "02_physics_earth", "03_chemistry_materials",
        "04_biology_health_literacy", "05_geography_environment", "06_history_civics",
        "07_economics_finance_literacy", "08_computing_internet",
        "09_language_writing_communication", "10_planning_social_reasoning",
    }
    assert all(fact["risk_class"] == "low" and fact["status"] == "PROMOTED" for fact in facts)


def test_enrichment_benchmark_covers_each_category_in_english_and_japanese():
    rows = [json.loads(line) for line in BENCHMARK_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 20
    for row in rows:
        result = answer_foundation(row["input"])
        assert result is not None, row["id"]
        assert result["fact_id"] == row["expected_fact_id"], row["id"]
        assert result["category"] == row["category"], row["id"]
        assert result["language"] == row["expected_language"], row["id"]


def test_high_stakes_or_current_questions_do_not_match_the_foundation_pack():
    assert answer_foundation("Should I buy this stock today?") is None
    assert answer_foundation("Which treatment should I take for my symptoms?") is None
    assert answer_foundation("Who is the current president?") is None
