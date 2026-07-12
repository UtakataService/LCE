from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.semantic_chunk import (
    MAX_CHUNKS,
    parse_semantic_chunks,
    run_semantic_chunk_benchmark,
    semantic_similarity,
)
from lce_validation.empirical.seed_graph import build_seed_graph


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "lce_validation" / "fixtures" / "semantic_chunk_v1_cases.jsonl"


class SemanticChunkTests(unittest.TestCase):
    def test_parser_is_deterministic(self) -> None:
        text = "Continue the previous design without changing the safety policy."
        self.assertEqual(parse_semantic_chunks(text), parse_semantic_chunks(text))

    def test_extracts_core_slots(self) -> None:
        chunk = parse_semantic_chunks("Implement a parser but keep the policy deterministic.")["chunks"][0]
        self.assertEqual(chunk["intent"], "request_implementation")
        self.assertEqual(chunk["predicate"], "implement")
        self.assertTrue(chunk["constraints"])
        self.assertTrue(chunk["semantic_signature"])

    def test_reference_is_visible(self) -> None:
        chunk = parse_semantic_chunks("Continue the previous approach.")["chunks"][0]
        self.assertIn("previous_turn", chunk["references"])

    def test_unresolved_reference_is_flagged(self) -> None:
        chunk = parse_semantic_chunks("Change it.")["chunks"][0]
        self.assertIn("anaphoric_it", chunk["references"])

    def test_chunk_count_is_bounded(self) -> None:
        result = parse_semantic_chunks(" ".join(f"Part {i}." for i in range(40)))
        self.assertEqual(result["chunk_count"], MAX_CHUNKS)
        self.assertTrue(result["limits"]["truncated"])

    def test_similarity_uses_explicit_features(self) -> None:
        left = parse_semantic_chunks("Implement a parser.")["chunks"][0]
        same = parse_semantic_chunks("Build a parser.")["chunks"][0]
        different = parse_semantic_chunks("Never delete files.")["chunks"][0]
        self.assertGreater(semantic_similarity(left, same), semantic_similarity(left, different))

    def test_english_first_claim_boundary_is_exposed(self) -> None:
        result = parse_semantic_chunks("これをcontinueして")
        self.assertEqual(result["chunks"][0]["language"], "mixed")
        self.assertIn("cross_lingual_semantic_equivalence", result["blocked_claims"])

    def test_benchmark_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_semantic_chunk_benchmark(CASES, Path(tmp))
        self.assertTrue(summary["ok"], summary)
        self.assertEqual(summary["case_count"], 20)
        self.assertEqual(summary["determinism_accuracy"], 1.0)

    def test_seed_graph_input_node_carries_semantics(self) -> None:
        graph = build_seed_graph("Implement a semantic parser.")
        node = next(item for item in graph["nodes"] if item["node_id"] == "input-01")
        self.assertEqual(node["intent"], "request_implementation")
        self.assertEqual(node["predicate"], "implement")
        self.assertTrue(node["semantic_signature"])

    def test_semantics_cannot_weaken_policy(self) -> None:
        graph = build_seed_graph("Please delete it without approval.")
        self.assertEqual(graph["policy_decision"], "DENY")
        self.assertEqual(graph["route"], "deny")


if __name__ == "__main__":
    unittest.main()
