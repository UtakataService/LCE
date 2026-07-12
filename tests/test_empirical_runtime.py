import json
import tempfile
import unittest
from pathlib import Path

from lce_validation.cli import run_empirical
from lce_validation.empirical.engine import run_empirical_slice


FIXTURES = Path("lce_validation/fixtures/empirical_poc_fixtures.jsonl")


class EmpiricalRuntimeTests(unittest.TestCase):
    def test_empirical_slice_outputs_required_rows(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "empirical01"
            summary = run_empirical_slice(FIXTURES, out)
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["fixture_count"], 6)
            self.assertEqual(summary["baseline_count"], 18)
            self.assertIn("ACCEPT_CAVEATED", summary["decision_counts"])
            self.assertIn("REPAIR_CLARIFY", summary["decision_counts"])
            self.assertTrue((out / "replay_manifest.json").exists())
            self.assertTrue((out / "baseline_runs.jsonl").exists())
            self.assertTrue((out / "acceptance_results.jsonl").exists())

    def test_empirical_cli_returns_success(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "empirical_cli"
            self.assertEqual(run_empirical(str(FIXTURES), str(out)), 0)
            summary = json.loads((out / "empirical_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["release_decision"], "schema_contract_ready")

    def test_unsupported_claim_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "empirical_claim"
            run_empirical_slice(FIXTURES, out)
            rows = [
                json.loads(line)
                for line in (out / "acceptance_results.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            by_fixture = {row["fixture_id"]: row for row in rows}
            self.assertEqual(by_fixture["FX-EMP-UNSUPPORTED-001"]["verdict"], "REJECT_UNSUPPORTED")
            self.assertIn("red_line_claim_without_row_evidence", by_fixture["FX-EMP-UNSUPPORTED-001"]["blocking_reasons"])
