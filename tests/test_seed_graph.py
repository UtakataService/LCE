import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.seed_graph import (
    EDGE_TYPES,
    NODE_TYPES,
    REQUIRED_CUBE_FACES,
    build_seed_graph,
    run_seed_graph_benchmark,
)


class SeedGraphTests(unittest.TestCase):
    def test_builds_required_node_types(self):
        result = build_seed_graph("Continue this chunk seed graph approach.", [{"speaker": "user", "text": "Use chunk seeds and graph edges for dialogue."}])
        node_types = {node["node_type"] for node in result["nodes"]}
        for node_type in NODE_TYPES:
            self.assertIn(node_type, node_types)
        self.assertTrue(result["output_support"]["ok"])

    def test_deterministic_replay(self):
        history = [{"speaker": "user", "text": "Use chunk seeds and graph edges for dialogue."}]
        first = build_seed_graph("Continue this chunk seed graph approach.", history)
        second = build_seed_graph("Continue this chunk seed graph approach.", history)
        self.assertEqual(first, second)

    def test_policy_block_is_monotonic_edge(self):
        result = build_seed_graph("Delete the file now.", [{"speaker": "user", "text": "Keep graph traces."}])
        self.assertEqual(result["route"], "deny")
        edge_types = {edge["edge_type"] for edge in result["edges"]}
        self.assertIn("policy_blocks", edge_types)
        self.assertTrue(result["output_support"]["ok"])

    def test_contradiction_repair_edge(self):
        result = build_seed_graph("Make safety gates random when the seed says so.", [{"speaker": "user", "text": "Safety gates must remain deterministic."}])
        self.assertEqual(result["route"], "contradiction_repair")
        edge_types = {edge["edge_type"] for edge in result["edges"]}
        self.assertIn("conflict", edge_types)
        self.assertIn("repairs", edge_types)

    def test_cube_disabled_by_default(self):
        result = build_seed_graph("Continue this graph approach.")
        self.assertNotIn("cube", result)
        self.assertEqual(result["cube_schema_version"], "")
        self.assertNotIn("cube_coords", result["nodes"][0])

    def test_cube_enabled_adds_projection_metadata_without_changing_route(self):
        plain = build_seed_graph("Write a Python function solve(numbers).", task_hint="coding")
        cube = build_seed_graph("Write a Python function solve(numbers).", task_hint="coding", enable_cube=True)
        self.assertEqual(plain["route"], cube["route"])
        self.assertIn("cube", cube)
        self.assertIn("cube_coords", cube["nodes"][0])
        faces = {face["face_id"] for face in cube["cube"]["faces"]}
        for face in REQUIRED_CUBE_FACES:
            self.assertIn(face, faces)

    def test_seed_graph_benchmark(self):
        cases = Path("lce_validation/fixtures/seed_graph_cases.jsonl")
        with tempfile.TemporaryDirectory() as td:
            summary = run_seed_graph_benchmark(cases, Path(td) / "out")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["case_count"], 5)
            self.assertEqual(summary["case_accuracy"], 1.0)


class SeedGraphContractTests(unittest.TestCase):
    def test_known_edge_types_are_declared(self):
        result = build_seed_graph("Write a Python function solve(numbers).", task_hint="coding", enable_cube=True)
        for edge in result["edges"]:
            self.assertIn(edge["edge_type"], EDGE_TYPES)
