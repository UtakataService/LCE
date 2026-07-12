import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.coding_task_runner import (
    run_coding_task,
    run_coding_task_benchmark,
    validate_candidate,
    verify_candidate,
)


class CodingTaskRunnerTests(unittest.TestCase):
    def test_sum_task_passes(self):
        result = run_coding_task("Write a Python function solve(numbers) that returns the sum of a list.")
        self.assertEqual(result["route"], "coding_pass")
        self.assertTrue(result["verification"]["ok"])
        self.assertIn("def solve", result["code"])

    def test_unknown_task_clarifies(self):
        result = run_coding_task("Build a web scraper that downloads pages.")
        self.assertEqual(result["route"], "coding_clarify")
        self.assertFalse(result["verification"]["ok"])

    def test_validation_blocks_imports(self):
        result = validate_candidate("import os\ndef solve(x):\n    return x\n", "solve")
        self.assertFalse(result["ok"])
        self.assertIn("imports_not_allowed", result["errors"])

    def test_validation_blocks_dunder_escape_and_reflection(self):
        dunder=validate_candidate("def solve(x):\n    return x.__class__.__base__\n", "solve")
        reflection=validate_candidate("def solve(x):\n    return getattr(x, 'open', None)\n", "solve")
        self.assertFalse(dunder["ok"])
        self.assertFalse(reflection["ok"])

    def test_verification_rejects_empty_test_set(self):
        result=verify_candidate({"function_name":"solve","code":"def solve(x):\n    return 999\n","tests":[]})
        self.assertFalse(result["ok"])
        self.assertEqual("tests_required",result["reason"])

    def test_coding_benchmark(self):
        cases = Path("lce_validation/fixtures/coding_task_cases.jsonl")
        with tempfile.TemporaryDirectory() as td:
            summary = run_coding_task_benchmark(cases, Path(td) / "out")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["case_count"], 4)
            self.assertEqual(summary["case_accuracy"], 1.0)
