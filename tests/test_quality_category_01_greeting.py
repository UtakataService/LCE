import json
from pathlib import Path
from lce_validation.runtime.japanese_dialogue import respond_japanese


ROOT=Path("lce_validation/fixtures")


def test_greeting_candidates_have_explicit_promote_or_quarantine_decisions():
    rows=[json.loads(x) for x in (ROOT / "quality_category_01_greeting_candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["decision"] for row in rows] == ["PROMOTE","PROMOTE","QUARANTINE","QUARANTINE"]


def test_greeting_holdout_uses_promoted_data_and_not_quarantined_assumptions():
    rows=[json.loads(x) for x in (ROOT / "quality_category_01_greeting_holdout.jsonl").read_text(encoding="utf-8").splitlines()]
    for row in rows:
        result=respond_japanese(row["input"],[])
        assert result["dialogue_act"] == row["expected_act"]
        assert result["evidence_id"] == row["expected_evidence_id"]
    assert respond_japanese("久しぶり",[])["match_decision"] == "UNKNOWN"
