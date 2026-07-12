import json
from pathlib import Path

from lce_validation.runtime.japanese_dialogue import respond_japanese


ROOT = Path("lce_validation/fixtures")


def test_ten_loop_ledger_has_audit_decision_for_every_candidate():
    rows=[json.loads(line) for line in (ROOT / "quality_wave1_loop2_candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["loop"] for row in rows] == list(range(1, 11))
    assert sum(row["decision"] == "PROMOTE" for row in rows) == 5
    assert all(row["reason"] for row in rows)


def test_promoted_candidates_are_live_and_quarantined_candidates_are_not():
    promoted=[("具体例を一つ示して","example_request"),("利点と欠点を並べて","tradeoff_request"),("制約を先に確認して","constraint_request"),("優先順位を決めたい","priority_request"),("前提が足りない気がする","premise_gap_acknowledgement")]
    for text, act in promoted:
        assert respond_japanese(text, [])["dialogue_act"] == act
    assert respond_japanese("絶対に正しいと断言して", [])["match_decision"] == "UNKNOWN"
