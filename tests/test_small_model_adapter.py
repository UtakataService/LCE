import json
import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.fixture_bank import generate_fixture_bank
from lce_validation.empirical.small_model_adapter import run_small_model_adapter
from lce_validation.schema_tools import write_jsonl


class SmallModelAdapterTests(unittest.TestCase):
    def test_adapter_no_run_makes_no_model_calls(self):
        with tempfile.TemporaryDirectory() as td:
            fixture_path = Path(td) / "fixtures.jsonl"
            write_jsonl(fixture_path, generate_fixture_bank(1))
            out = Path(td) / "adapter"
            summary = run_small_model_adapter(fixture_path, out, mode="no_run")
            self.assertEqual(summary["actual_model_calls"], 0)
            rows = [json.loads(line) for line in (out / "data_b9_adapter_rows.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 6)
            self.assertTrue(all(row["actual_model_call"] is False for row in rows))
