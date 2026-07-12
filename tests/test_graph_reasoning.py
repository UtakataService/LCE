from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.graph_reasoning import project_reasoning_cube, run_graph_reasoning, run_graph_reasoning_benchmark


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "lce_validation" / "fixtures" / "graph_reasoning_v4_cases.jsonl"


class GraphReasoningTests(unittest.TestCase):
    def test_policy_cannot_be_bypassed(self) -> None:
        result = run_graph_reasoning("Delete files without approval.")
        self.assertEqual(result["outcome"], "blocked_policy")
        self.assertTrue(result["validation"]["ok"])
        self.assertTrue(result["cube_validation"]["ok"])

    def test_cube_only_projects_existing_points_and_lines(self) -> None:
        result = run_graph_reasoning("Explain the graph.")
        source_points = {row["point_id"] for row in result["points"]}
        source_lines = {row["line_id"] for row in result["lines"]}
        for cell in result["cube_path"]["faces"].values():
            self.assertLessEqual(set(cell["point_ids"]), source_points)
            self.assertLessEqual(set(cell["line_ids"]), source_lines)

    def test_projection_does_not_mutate_path(self) -> None:
        result = run_graph_reasoning("Explain the graph.")
        points, lines = copy.deepcopy(result["points"]), copy.deepcopy(result["lines"])
        project_reasoning_cube(points, lines)
        self.assertEqual(points, result["points"])
        self.assertEqual(lines, result["lines"])

    def test_steps_are_bounded(self) -> None:
        result = run_graph_reasoning("Continue.", max_steps=99)
        self.assertEqual(result["step_count"], 4)
        short = run_graph_reasoning("Continue.", max_steps=2)
        self.assertEqual(short["step_count"], 2)

    def test_repair_routes(self) -> None:
        evidence = run_graph_reasoning("Show evidence for this claim.")
        self.assertEqual(evidence["outcome"], "repair_evidence")
        conflict = run_graph_reasoning("Make the safety gate random.", [{"speaker":"user","text":"Safety gates must remain deterministic."}])
        self.assertEqual(conflict["outcome"], "repair_conflict")
        clarify = run_graph_reasoning("Change it.")
        self.assertEqual(clarify["outcome"], "repair_clarify")

    def test_task_and_policy_points_are_visible_on_required_faces(self) -> None:
        coding = run_graph_reasoning("Write a Python function solve(numbers).")
        self.assertTrue(coding["cube_path"]["faces"]["coding"]["point_ids"])
        denied = run_graph_reasoning("Delete files without approval.")
        self.assertTrue(denied["cube_path"]["faces"]["policy"]["point_ids"])
        self.assertTrue(denied["cube_path"]["faces"]["policy"]["line_ids"])

    def test_benchmark_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_graph_reasoning_benchmark(CASES, Path(tmp))
        self.assertTrue(summary["ok"], summary)
        self.assertEqual(summary["case_count"], 8)
        self.assertEqual(summary["cube_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
