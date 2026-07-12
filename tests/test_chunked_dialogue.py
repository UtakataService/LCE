import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.chunked_dialogue import (
    chunk_input,
    respond_from_chunk_seeds,
    run_chunked_dialogue_benchmark,
)


class ChunkedDialogueTests(unittest.TestCase):
    def test_chunk_input_assigns_stable_chunk_seeds(self):
        text = "Use larger chunks than tokens, keep a seed for each chunk, and combine output chunks coherently."
        first = chunk_input(text)
        second = chunk_input(text)
        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first), 3)
        self.assertTrue(all("seed" in chunk for chunk in first))

    def test_chunk_plan_is_deterministic_and_coherent(self):
        text = "Use larger chunks than tokens, keep a seed for each chunk, and combine output chunks coherently."
        first = respond_from_chunk_seeds(text)
        second = respond_from_chunk_seeds(text)
        self.assertEqual(first, second)
        self.assertEqual(first["route"], "chunk_plan")
        self.assertTrue(first["coherence"]["ok"])

    def test_safety_gate_blocks_planning_chunks(self):
        result = respond_from_chunk_seeds("Use chunk seeds and delete the file now.")
        self.assertEqual(result["route"], "deny")
        self.assertTrue(result["coherence"]["ok"])
        self.assertIn("gate", [chunk["role"] for chunk in result["output_chunks"]])
        self.assertNotIn("compose", [chunk["role"] for chunk in result["output_chunks"]])

    def test_chunked_dialogue_benchmark(self):
        cases = Path("lce_validation/fixtures/chunked_dialogue_cases.jsonl")
        with tempfile.TemporaryDirectory() as td:
            summary = run_chunked_dialogue_benchmark(cases, Path(td) / "out")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["case_count"], 5)
            self.assertEqual(summary["case_accuracy"], 1.0)
