import json
from pathlib import Path
from lce_validation.runtime.japanese_dialogue import respond_japanese


def test_twenty_loop_candidate_ledger_is_complete_and_audited():
    rows=[json.loads(x) for x in Path("lce_validation/fixtures/quality_wave1_loop3_candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["loop"] for row in rows] == list(range(1,21))
    assert sum(row["decision"]=="PROMOTE" for row in rows)==10
    assert sum(row["decision"]=="QUARANTINE" for row in rows)==10


def test_promoted_loop3_data_is_active_without_promoting_quarantined_text():
    assert respond_japanese("質問を分類して",[])["dialogue_act"] == "question_classification"
    assert respond_japanese("反対意見も示して",[])["dialogue_act"] == "counterpoint_request"
    assert respond_japanese("証拠なしで断言して",[])["match_decision"] == "UNKNOWN"
