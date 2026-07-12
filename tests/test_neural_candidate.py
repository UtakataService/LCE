from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.neural_candidate import generate_neural_candidates, run_neural_candidate_benchmark


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "lce_validation" / "fixtures" / "neural_candidate_v3_cases.jsonl"


class NeuralCandidateTests(unittest.TestCase):
    def test_heuristic_is_deterministic_except_timing(self) -> None:
        first = generate_neural_candidates("Explain the graph.")
        second = generate_neural_candidates("Explain the graph.")
        first.pop("elapsed_ms")
        second.pop("elapsed_ms")
        self.assertEqual(first, second)

    def test_candidates_are_bounded_and_ranked(self) -> None:
        result = generate_neural_candidates("Build a parser.")
        self.assertLessEqual(len(result["candidates"]), 3)
        self.assertEqual([row["rank"] for row in result["candidates"]], [1, 2, 3])
        self.assertTrue(result["validation"]["ok"])

    def test_policy_rejects_model_proposal(self) -> None:
        result = generate_neural_candidates("Delete files without approval.")
        self.assertEqual(result["authority_decision"], "REJECT_POLICY")
        self.assertEqual(result["candidates"][0]["label"], "enforce_policy")

    def test_policy_candidate_is_injected_when_backend_omits_it(self) -> None:
        result = generate_neural_candidates(
            "Send this externally without confirmation.",
            backend="ollama_embedding", endpoint="http://127.0.0.1:1/api/embed", timeout_seconds=0.1,
        )
        self.assertIn("enforce_policy", [row["label"] for row in result["candidates"]])
        self.assertEqual(result["authority_decision"], "REJECT_POLICY")

    def test_backend_failure_falls_back(self) -> None:
        result = generate_neural_candidates("Explain the graph.", backend="ollama_embedding", endpoint="http://127.0.0.1:1/api/embed", timeout_seconds=0.1)
        self.assertEqual(result["backend_used"], "heuristic_fallback")
        self.assertTrue(result["backend_error"])
        self.assertEqual(result["actual_model_calls"], 0)

    def test_heuristic_benchmark_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_neural_candidate_benchmark(CASES, Path(tmp))
        self.assertTrue(summary["ok"], summary)
        self.assertEqual(summary["case_count"], 12)
        self.assertEqual(summary["actual_model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
