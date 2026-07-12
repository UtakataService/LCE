import json
from pathlib import Path

from lce_validation.runtime.flexible_response_evaluation import evaluate_fre_bank


def test_exposed_fre_bank_separates_safe_flexibility_from_hard_boundaries():
    path = Path("lce_validation/fixtures/flexible_response_envelope_exposed_v1.jsonl")
    fixtures = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = evaluate_fre_bank(fixtures)
    assert report["case_count"] == 8
    assert report["failed"] == 0
    assert report["safe_flexibility_count"] == report["low_risk_unknown_count"] == 2
