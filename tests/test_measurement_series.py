import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.fixture_bank import generate_fixture_bank
from lce_validation.empirical.measurement_series import run_measurement_series
from lce_validation.schema_tools import write_jsonl


class MeasurementSeriesTests(unittest.TestCase):
    def test_measurement_series_records_repeated_runs(self):
        rows = generate_fixture_bank(1)
        with tempfile.TemporaryDirectory() as td:
            fixture_path = Path(td) / "bank.jsonl"
            write_jsonl(fixture_path, rows)
            out = Path(td) / "measure"
            summary = run_measurement_series(fixture_path, out, repeats=2)
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["repeats"], 2)
            self.assertEqual(len(summary["runs"]), 2)
            self.assertTrue(summary["stable_decision_counts"])
            self.assertTrue(summary["stable_acceptance_counts"])
            self.assertGreater(summary["artifact_bytes"]["min"], 0)
            self.assertTrue((out / "measurement_runs.jsonl").exists())
            self.assertTrue((out / "measurement_series_summary.json").exists())

    def test_measurement_series_rejects_zero_repeats(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                run_measurement_series(Path(td) / "missing.jsonl", Path(td) / "out", repeats=0)
