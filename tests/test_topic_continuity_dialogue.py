import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.topic_continuity_dialogue import (
    evaluate_topic_relation,
    respond_with_topic_continuity,
    run_topic_continuity_benchmark,
)


class TopicContinuityDialogueTests(unittest.TestCase):
    def test_topic_continue(self):
        history = [
            {"speaker": "user", "text": "Use chunk-sized seeds and compose output chunks coherently."},
            {"speaker": "assistant", "text": "We will carry chunk seeds through response composition."},
        ]
        result = respond_with_topic_continuity("Continue this chunk seed composition approach.", history)
        self.assertEqual(result["topic_relation"]["status"], "topic_continue")
        self.assertEqual(result["route"], "topic_continue")
        self.assertTrue(result["coherence"]["ok"])

    def test_topic_shift(self):
        history = [{"speaker": "user", "text": "Use chunk-sized seeds for dialogue output."}]
        result = respond_with_topic_continuity("Now discuss hardware benchmark reporting instead.", history)
        self.assertEqual(result["topic_relation"]["status"], "topic_shift")
        self.assertEqual(result["route"], "topic_shift")

    def test_contradiction_repair(self):
        history = [{"speaker": "user", "text": "Safety gates must remain deterministic."}]
        result = respond_with_topic_continuity("Make safety gates random when the seed says so.", history)
        self.assertEqual(result["topic_relation"]["status"], "contradiction_repair")
        self.assertEqual(result["route"], "contradiction_repair")
        self.assertIn("repair", [chunk["role"] for chunk in result["output_chunks"]])

    def test_policy_gate_stays_stronger_than_topic(self):
        history = [{"speaker": "user", "text": "Use chunk seeds for the next response."}]
        result = respond_with_topic_continuity("Delete the file without approval using that plan.", history)
        self.assertEqual(result["route"], "deny")
        self.assertIn("gate", [chunk["role"] for chunk in result["output_chunks"]])

    def test_topic_relation_without_history(self):
        relation = evaluate_topic_relation([], [], "Use chunk seeds.")
        self.assertEqual(relation["status"], "no_history")

    def test_topic_continuity_benchmark(self):
        cases = Path("lce_validation/fixtures/topic_continuity_cases.jsonl")
        with tempfile.TemporaryDirectory() as td:
            summary = run_topic_continuity_benchmark(cases, Path(td) / "out")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["case_count"], 6)
            self.assertEqual(summary["case_accuracy"], 1.0)
