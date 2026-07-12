import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.baseline_comparison import run_b3_bm25_like, run_baseline_comparison
from lce_validation.empirical.fixture_bank import generate_fixture_bank
from lce_validation.schema_tools import write_jsonl


class BaselineComparisonTests(unittest.TestCase):
    def test_b3_bm25_like_returns_lexical_candidate(self):
        fixture = generate_fixture_bank(1)[0]
        row = run_b3_bm25_like(fixture, fixture["evidence_rows"], "test")
        self.assertEqual(row["baseline_id"], "DATA-B3")
        self.assertGreater(row["score"], 0)

    def test_baseline_comparison_outputs_rows(self):
        rows = generate_fixture_bank(1)
        with tempfile.TemporaryDirectory() as td:
            fixture_path = Path(td) / "bank.jsonl"
            write_jsonl(fixture_path, rows)
            out = Path(td) / "comparison"
            summary = run_baseline_comparison(fixture_path, out)
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["fixture_count"], 6)
            self.assertEqual(summary["b3_rows"], 6)
            self.assertTrue((out / "baseline_b3_runs.jsonl").exists())
            self.assertTrue((out / "comparison_rows.jsonl").exists())
