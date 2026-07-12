import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.rule_grounding import evaluate_action, parse_rule, run_rule_grounding_benchmark


class RuleGroundingTests(unittest.TestCase):
    def test_parse_prohibition_rule(self):
        rule = parse_rule("Do not delete files unless approval is present.")
        self.assertEqual(rule["rule_type"], "prohibition")
        self.assertEqual(rule["subject_action"], "delete_file")
        self.assertEqual(rule["gate_action"], "DENY")

    def test_evaluate_requires_confirmation(self):
        rule = parse_rule("Ask confirmation before sending external messages.")
        decision = evaluate_action(rule, {"action_type": "send_external_message", "user_confirmed": False})
        self.assertEqual(decision["decision"], "ASK_CONFIRMATION")

    def test_ambiguous_rule_clarifies(self):
        rule = parse_rule("Be careful with dangerous operations.")
        decision = evaluate_action(rule, {"action_type": "delete_file"})
        self.assertEqual(rule["rule_type"], "ambiguous")
        self.assertEqual(decision["decision"], "CLARIFY_RULE")

    def test_rule_grounding_benchmark(self):
        cases = Path("lce_validation/fixtures/rule_grounding_step1_cases.jsonl")
        with tempfile.TemporaryDirectory() as td:
            summary = run_rule_grounding_benchmark(cases, Path(td) / "out")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["case_count"], 7)
            self.assertEqual(summary["parse_accuracy"], 1.0)
            self.assertEqual(summary["decision_accuracy"], 1.0)
