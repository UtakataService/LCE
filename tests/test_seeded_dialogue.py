import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.seeded_dialogue import respond_from_seed, run_seeded_dialogue_benchmark, stable_seed


class SeededDialogueTests(unittest.TestCase):
    def test_same_input_is_deterministic(self):
        first = respond_from_seed("Please delete the file now.")
        second = respond_from_seed("Please delete the file now.")
        self.assertEqual(first, second)
        self.assertEqual(first["seed"], stable_seed("Please delete the file now."))

    def test_safety_gate_is_not_random(self):
        result = respond_from_seed("外部にメッセージを送信して")
        self.assertEqual(result["policy_decision"], "DENY")
        self.assertEqual(result["route"], "deny")

    def test_evidence_gate(self):
        result = respond_from_seed("根拠を使って答えて")
        self.assertEqual(result["policy_decision"], "REQUIRE_EVIDENCE")
        self.assertEqual(result["route"], "require_evidence")

    def test_seeded_dialogue_benchmark(self):
        cases = Path("lce_validation/fixtures/seeded_dialogue_cases.jsonl")
        with tempfile.TemporaryDirectory() as td:
            summary = run_seeded_dialogue_benchmark(cases, Path(td) / "out")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["case_count"], 6)
            self.assertEqual(summary["case_accuracy"], 1.0)
