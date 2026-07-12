import json
import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.entailment import infer_support_state
from lce_validation.empirical.engine import run_empirical_slice


FIXTURES = Path("lce_validation/fixtures/entailment_expansion_fixtures.jsonl")


def _fixtures() -> dict[str, dict]:
    rows = [json.loads(line) for line in FIXTURES.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["fixture_id"]: row for row in rows}


class EntailmentExpansionTests(unittest.TestCase):
    def test_support_can_be_inferred_without_manual_support_flag(self):
        fixture = _fixtures()["FX-ENTAIL-INFERRED-SUPPORT-001"]
        evidence = fixture["evidence_rows"][0]
        self.assertNotIn("supports", evidence)
        result = infer_support_state(fixture, evidence)
        self.assertEqual(result["support_state"], "supports")

    def test_overlap_without_required_terms_is_unknown(self):
        fixture = _fixtures()["FX-ENTAIL-LEXICAL-OVERLAP-UNKNOWN-001"]
        result = infer_support_state(fixture, fixture["evidence_rows"][0])
        self.assertEqual(result["support_state"], "unknown")

    def test_entailment_run_preserves_outcomes(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "entailment01"
            summary = run_empirical_slice(FIXTURES, out)
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["fixture_count"], 3)
            self.assertEqual(summary["decision_counts"]["ACCEPT_CAVEATED"], 1)
            self.assertEqual(summary["decision_counts"]["UNKNOWN_MODEL_GAP"], 1)
            self.assertEqual(summary["decision_counts"]["REJECT_UNSUPPORTED"], 1)
            rows = [
                json.loads(line)
                for line in (out / "decision_rows.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            inferred = rows[0]["decision_inputs"]["inferred_support"][0]
            self.assertEqual(inferred["support_state"], "supports")
