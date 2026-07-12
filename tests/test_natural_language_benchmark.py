import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.fixture_bank import generate_fixture_bank
from lce_validation.empirical.natural_language_benchmark import run_natural_language_benchmark
from lce_validation.empirical.nl_normalization import normalize_tokens
from lce_validation.schema_tools import write_jsonl


class NaturalLanguageBenchmarkTests(unittest.TestCase):
    def test_normalize_tokens_maps_small_aliases(self):
        self.assertIn("port", normalize_tokens("What is alpha1 listening on?"))
        self.assertIn("approval", normalize_tokens("no sign off"))

    def test_natural_language_benchmark_scores_cases(self):
        fixtures = generate_fixture_bank(2)
        cases = [
            {
                "case_id": "T-SUP",
                "query": "What is alpha1 listening on?",
                "expected_route": "answer_with_caveat",
                "expected_outcome": "ACCEPT_CAVEATED",
                "expected_fixture_id": "FX-BANK-SUPPORTED-001",
                "phenomenon_tags": ["english_paraphrase"],
            },
            {
                "case_id": "T-OOD",
                "query": "Who won the chess tournament yesterday?",
                "expected_route": "out_of_domain",
                "expected_outcome": "UNKNOWN_MODEL_GAP",
                "expected_fixture_id": None,
                "phenomenon_tags": ["english_out_of_domain"],
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            fixture_path = Path(td) / "fixtures.jsonl"
            benchmark_path = Path(td) / "nl.jsonl"
            write_jsonl(fixture_path, fixtures)
            write_jsonl(benchmark_path, cases)
            summary = run_natural_language_benchmark(fixture_path, benchmark_path, Path(td) / "out")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["case_accuracy"], 1.0)
            self.assertTrue((Path(td) / "out" / "natural_language_benchmark_rows.jsonl").exists())
