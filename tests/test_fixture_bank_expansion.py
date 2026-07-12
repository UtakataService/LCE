import json
import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.fixture_bank import generate_fixture_bank
from lce_validation.empirical.engine import run_empirical_slice
from lce_validation.schema_tools import write_jsonl


class FixtureBankExpansionTests(unittest.TestCase):
    def test_fixture_bank_has_sixty_rows_and_six_families(self):
        rows = generate_fixture_bank()
        self.assertEqual(len(rows), 60)
        tags = {row["phenomenon_tags"][0] for row in rows}
        self.assertEqual(len(tags), 6)

    def test_fixture_bank_run_covers_all_primary_outcomes(self):
        rows = generate_fixture_bank(2)
        with tempfile.TemporaryDirectory() as td:
            fixture_path = Path(td) / "bank.jsonl"
            write_jsonl(fixture_path, rows)
            out = Path(td) / "bankrun"
            summary = run_empirical_slice(fixture_path, out)
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["fixture_count"], 12)
            for outcome in ["ACCEPT_CAVEATED", "UNKNOWN_MODEL_GAP", "REJECT_UNSUPPORTED", "REPAIR_RETRIEVE", "REPAIR_CLARIFY"]:
                self.assertIn(outcome, summary["decision_counts"])

    def test_generated_bank_rows_are_json_serializable(self):
        rows = generate_fixture_bank(1)
        encoded = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
        self.assertIn("FX-BANK-SUPPORTED-001", encoded)
