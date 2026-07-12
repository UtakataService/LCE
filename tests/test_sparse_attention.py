from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.seed_graph import build_seed_graph
from lce_validation.empirical.sparse_attention import run_sparse_attention_benchmark, select_sparse_attention


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "lce_validation" / "fixtures" / "sparse_attention_v2_cases.jsonl"


class SparseAttentionTests(unittest.TestCase):
    def test_is_deterministic(self) -> None:
        args = ("Continue graph verification.", [{"speaker": "user", "text": "Graph verification is active."}])
        self.assertEqual(build_seed_graph(*args), build_seed_graph(*args))

    def test_policy_edge_survives_zero_soft_budget(self) -> None:
        graph = build_seed_graph("Delete files without approval.", attention_limits={"max_selected": 1, "top_k_per_target": 0})
        attention = graph["sparse_attention"]
        self.assertTrue(attention["invariants"]["hard_edges_preserved"])
        self.assertTrue(any(row["selected"] and row["edge_type"] == "policy_blocks" for row in attention["candidates"]))

    def test_output_support_survives_tight_budget(self) -> None:
        graph = build_seed_graph("Continue.", attention_limits={"max_selected": 0, "top_k_per_target": 0})
        self.assertTrue(graph["output_support"]["ok"])
        self.assertTrue(graph["sparse_attention"]["invariants"]["output_support_preserved"])

    def test_hard_overflow_is_visible(self) -> None:
        graph = build_seed_graph("Write a Python function and show evidence.", task_hint="coding", attention_limits={"max_selected": 1})
        self.assertTrue(graph["sparse_attention"]["hard_budget_overflow"])
        self.assertGreater(graph["sparse_attention"]["selected_count"], 1)

    def test_candidate_truncation_cannot_drop_late_hard_edge(self) -> None:
        nodes = [
            {"node_id":"a","node_type":"input_chunk","text":"a","role":"user","turn_index":0},
            {"node_id":"b","node_type":"output_chunk","text":"b","role":"assistant","turn_index":0},
        ]
        edges = [
            {"edge_id":"soft","edge_type":"topic_shift","from_node":"a","to_node":"b","score":0.2},
            {"edge_id":"hard","edge_type":"supports_output","from_node":"a","to_node":"b","score":1.0},
        ]
        result = select_sparse_attention(nodes, edges, max_candidates=1)
        self.assertTrue(result["ok"])
        self.assertEqual(result["selected_edge_ids"], ["hard"])
        self.assertTrue(result["candidate_truncated"])

    def test_ties_use_candidate_id(self) -> None:
        nodes = [
            {"node_id":"a","node_type":"history_chunk","text":"alpha","role":"user","turn_index":0},
            {"node_id":"b","node_type":"history_chunk","text":"beta","role":"user","turn_index":0},
            {"node_id":"t","node_type":"input_chunk","text":"target","role":"user","turn_index":1},
        ]
        edges = [
            {"edge_id":"z","edge_type":"topic_shift","from_node":"a","to_node":"t","score":0.5},
            {"edge_id":"a","edge_type":"topic_shift","from_node":"b","to_node":"t","score":0.5},
        ]
        result = select_sparse_attention(nodes, edges, max_selected=1, top_k_per_target=1)
        self.assertEqual(result["selected_edge_ids"], ["a"])

    def test_benchmark_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_sparse_attention_benchmark(CASES, Path(tmp))
        self.assertTrue(summary["ok"], summary)
        self.assertEqual(summary["case_count"], 8)
        self.assertEqual(summary["hard_preservation_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
