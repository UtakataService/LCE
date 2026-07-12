import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.fixture_bank import generate_fixture_bank
from lce_validation.empirical.hardware_benchmark_validation import run_hardware_benchmark_validation
from lce_validation.schema_tools import write_jsonl
from lce_validation.systems.hardware_profile import local_hardware_profile, raspberry_pi_boundary_profile


class HardwareBenchmarkValidationTests(unittest.TestCase):
    def test_local_hardware_profile_has_lane_and_cpu(self):
        profile = local_hardware_profile()
        self.assertEqual(profile["lane_label"], "WIN_CPU_FIRST")
        self.assertIsNotNone(profile["cpu_count_logical"])

    def test_pi_boundary_profile_is_non_impacting(self):
        profile = raspberry_pi_boundary_profile()
        self.assertEqual(profile["lane_label"], "RASPI5_BOUNDARY")
        self.assertEqual(profile["impact"], "none")
        self.assertEqual(profile["status"], "not_measured")

    def test_hardware_benchmark_validation_emits_gates(self):
        rows = generate_fixture_bank(1)
        with tempfile.TemporaryDirectory() as td:
            fixture_path = Path(td) / "bank.jsonl"
            write_jsonl(fixture_path, rows)
            out = Path(td) / "validation"
            summary = run_hardware_benchmark_validation(fixture_path, out, repeats=2, thresholds={"required_repeats": 2})
            self.assertTrue(summary["ok"])
            self.assertIn("windows_cpu_first_local_benchmark_lane", summary["accepted_claims"])
            self.assertIn("raspberry_pi_sufficiency", summary["blocked_claims"])
            self.assertTrue((out / "hardware_profile.json").exists())
            self.assertTrue((out / "hardware_benchmark_validation_summary.json").exists())
