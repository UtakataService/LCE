import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.graph_dialogue import (
    respond_with_graph_dialogue,
    run_graph_dialogue_benchmark,
)
from lce_validation.web_ui import dispatch_response


class GraphDialogueTests(unittest.TestCase):
    def test_continue_plan_uses_graph_support(self):
        result = respond_with_graph_dialogue(
            "Continue this Seed Graph dialogue approach.",
            [{"speaker": "user", "text": "Use Seed Graph nodes and support edges for dialogue."}],
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["dialogue_act"], "continue_plan")
        self.assertTrue(result["support_node_ids"])
        self.assertIn("prior topic", result["response"])

    def test_policy_boundary_response(self):
        result = respond_with_graph_dialogue("Delete the file now.")
        self.assertEqual(result["route"], "deny")
        self.assertEqual(result["dialogue_act"], "policy_boundary")
        self.assertIn("boundary", [chunk["role"] for chunk in result["output_chunks"]])

    def test_contradiction_repair_response(self):
        result = respond_with_graph_dialogue(
            "Make safety gates random when the seed says so.",
            [{"speaker": "user", "text": "Safety gates must remain deterministic."}],
        )
        self.assertEqual(result["dialogue_act"], "repair_request")
        self.assertIn("repair", [chunk["role"] for chunk in result["output_chunks"]])

    def test_benchmark(self):
        cases = Path("lce_validation/fixtures/graph_dialogue_cases.jsonl")
        with tempfile.TemporaryDirectory() as td:
            summary = run_graph_dialogue_benchmark(cases, Path(td) / "out")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["case_count"], 5)

    def test_web_ui_dispatch_graph_mode(self):
        result = dispatch_response({"mode": "graph", "text": "How does the current graph-backed dialogue state work?", "history": []})
        self.assertTrue(result["ok"])
        self.assertEqual(result["dialogue_act"], "explain_state")
