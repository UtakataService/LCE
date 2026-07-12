import json
from pathlib import Path


ROOT=Path("lce_validation/fixtures")


def test_remaining_nineteen_categories_have_audited_data_loop_records():
    rows=[json.loads(x) for x in (ROOT / "quality_category_campaign_02_20.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows)==19
    assert {row["category_id"].split("_",1)[0] for row in rows} == {f"{i:02d}" for i in range(2,21)}
    for row in rows:
        assert row["promote_ref"] and row["quarantine_reason"] and row["holdout_ref"] and row["kpt"]
        assert row["status"] == "COMPLETE"


def test_remaining_nineteen_categories_have_candidate_quarantine_and_holdout_data():
    rows=[json.loads(x) for x in (ROOT / "quality_category_campaign_02_20_records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 19
    for row in rows:
        assert row["candidate"]["decision"] == "PROMOTE"
        assert row["candidate"]["input"] and row["candidate"]["response"]
        assert row["quarantine"]["input"] and row["quarantine"]["reason"]
        assert row["holdout"]["input"] and row["holdout"]["expected"]
