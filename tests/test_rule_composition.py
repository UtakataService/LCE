import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.rule_composition import compose_rules, run_rule_composition_benchmark


class RuleCompositionTests(unittest.TestCase):
    def test_high_priority_deny_wins(self):
        result = compose_rules(
            [
                {"rule_id": "confirm", "priority": 10, "rule_text": "Ask confirmation before sending external messages."},
                {"rule_id": "deny", "priority": 100, "rule_text": "Do not send external messages unless approval is present."},
            ],
            {"action_type": "send_external_message", "approval_present": False, "user_confirmed": False},
        )
        self.assertEqual(result["decision"], "DENY")
        self.assertEqual(result["winning_rule_id"], "deny")

    def test_same_priority_conflict(self):
        result = compose_rules(
            [
                {"rule_id": "confirm", "priority": 50, "rule_text": "Ask confirmation before sending external messages."},
                {"rule_id": "deny", "priority": 50, "rule_text": "Do not send external messages unless approval is present."},
            ],
            {"action_type": "send_external_message", "approval_present": False, "user_confirmed": False},
        )
        self.assertEqual(result["decision"], "CONFLICT")
        self.assertIsNone(result["winning_rule_id"])

    def test_default_policy_applies_when_no_rule_matches(self):
        result = compose_rules(
            [{"rule_id": "evidence", "priority": 10, "rule_text": "Only answer from evidence when evidence is available."}],
            {"action_type": "send_external_message", "evidence_present": True},
            default_policy="DENY",
        )
        self.assertEqual(result["decision"], "DENY")
        self.assertIsNone(result["winning_rule_id"])

    def test_rule_composition_benchmark(self):
        cases = Path("lce_validation/fixtures/rule_grounding_step2_multirule_cases.jsonl")
        with tempfile.TemporaryDirectory() as td:
            summary = run_rule_composition_benchmark(cases, Path(td) / "out")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["case_count"], 7)
            self.assertEqual(summary["case_accuracy"], 1.0)
