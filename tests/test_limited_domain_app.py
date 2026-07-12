import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.fixture_bank import generate_fixture_bank
from lce_validation.empirical.limited_domain_app import answer_limited_domain
from lce_validation.schema_tools import write_jsonl


class LimitedDomainAppTests(unittest.TestCase):
    def test_answers_supported_fixture_by_id(self):
        rows = generate_fixture_bank(1)
        with tempfile.TemporaryDirectory() as td:
            fixture_path = Path(td) / "bank.jsonl"
            write_jsonl(fixture_path, rows)
            result = answer_limited_domain(fixture_path, rows[0]["fixture_id"])
            self.assertEqual(result["route"], "answer_with_caveat")
            self.assertEqual(result["outcome"], "ACCEPT_CAVEATED")
            self.assertTrue(result["evidence_refs"])

    def test_routes_out_of_domain_query(self):
        rows = generate_fixture_bank(1)
        with tempfile.TemporaryDirectory() as td:
            fixture_path = Path(td) / "bank.jsonl"
            write_jsonl(fixture_path, rows)
            result = answer_limited_domain(fixture_path, "zzzz qqqq no matching domain tokens")
            self.assertEqual(result["route"], "out_of_domain")
            self.assertIsNone(result["matched_fixture_id"])

    def test_writes_result_artifact(self):
        rows = generate_fixture_bank(1)
        with tempfile.TemporaryDirectory() as td:
            fixture_path = Path(td) / "bank.jsonl"
            out_path = Path(td) / "answer.json"
            write_jsonl(fixture_path, rows)
            result = answer_limited_domain(fixture_path, rows[-1]["fixture_id"], out_path=out_path)
            self.assertTrue(out_path.exists())
            self.assertIn(result["route"], {"ask_clarifying_question", "retrieve_more_evidence", "model_gap", "reject_unsupported"})
