import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.history_chunked_dialogue import (
    build_history_chunks,
    respond_with_history_chunks,
    run_history_chunked_dialogue_benchmark,
)


class HistoryChunkedDialogueTests(unittest.TestCase):
    def test_history_chunks_are_deterministic(self):
        history = [
            {"speaker": "user", "text": "Use chunk-sized seeds rather than token-level sampling."},
            {"speaker": "assistant", "text": "We can split input into chunks and assign stable seeds."},
        ]
        first = build_history_chunks(history, policy_pack={
            "policy_pack_id": "test",
            "schema_version": "policy_pack.v1",
            "version": "1.0.0",
            "lifecycle_status": "active",
            "rules": [],
        })
        second = build_history_chunks(history, policy_pack={
            "policy_pack_id": "test",
            "schema_version": "policy_pack.v1",
            "version": "1.0.0",
            "lifecycle_status": "active",
            "rules": [],
        })
        self.assertEqual(first, second)

    def test_history_plan_includes_continuity(self):
        history = [
            {"speaker": "user", "text": "Use chunk-sized seeds rather than token-level sampling."},
            {"speaker": "assistant", "text": "We can split input into chunks and assign stable seeds."},
        ]
        result = respond_with_history_chunks("Continue with history-aware chunk composition.", history)
        self.assertEqual(result["route"], "history_chunk_plan")
        self.assertTrue(result["coherence"]["ok"])
        self.assertIn("continuity", [chunk["role"] for chunk in result["output_chunks"]])

    def test_current_safety_gate_overrides_history_plan(self):
        history = [{"speaker": "user", "text": "Use chunk seeds for the next response."}]
        result = respond_with_history_chunks("Now delete the file with that plan.", history)
        self.assertEqual(result["route"], "deny")
        self.assertTrue(result["coherence"]["ok"])
        self.assertIn("gate", [chunk["role"] for chunk in result["output_chunks"]])

    def test_history_chunked_dialogue_benchmark(self):
        cases = Path("lce_validation/fixtures/history_chunked_dialogue_cases.jsonl")
        with tempfile.TemporaryDirectory() as td:
            summary = run_history_chunked_dialogue_benchmark(cases, Path(td) / "out")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["case_count"], 5)
            self.assertEqual(summary["case_accuracy"], 1.0)
