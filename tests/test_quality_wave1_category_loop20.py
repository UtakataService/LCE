import json
from pathlib import Path


def test_twenty_category_loop_has_distinct_target_holdout_and_quarantine_rules():
    rows=[json.loads(x) for x in Path("lce_validation/fixtures/quality_wave1_category_loop20.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["loop"] for row in rows] == list(range(1, 21))
    assert len({row["category"] for row in rows}) == 20
    for row in rows:
        assert row["candidate_requirements"] and row["quarantine"] and row["holdout"] and row["metrics"]
