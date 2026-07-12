import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.policy_pack_lifecycle import (
    activate_policy_pack,
    evaluate_policy_pack,
    run_policy_pack_lifecycle_benchmark,
    validate_policy_pack,
)


class PolicyPackLifecycleTests(unittest.TestCase):
    def test_active_pack_evaluates_existing_rule_composition(self):
        pack = {
            "policy_pack_id": "conversation-safety-v1",
            "schema_version": "policy_pack.v1",
            "version": "1.0.0",
            "lifecycle_status": "active",
            "min_engine_version": "lce-policy-lifecycle-v0",
            "rules": [
                {"rule_id": "external-confirm", "priority": 10, "rule_text": "Ask confirmation before sending external messages."},
                {"rule_id": "external-approval", "priority": 100, "rule_text": "Do not send external messages unless approval is present."},
            ],
        }
        result = evaluate_policy_pack(pack, {"action_type": "send_external_message", "approval_present": False, "user_confirmed": False})
        self.assertEqual(result["activation"]["activation_state"], "active")
        self.assertEqual(result["decision"], "DENY")
        self.assertEqual(result["winning_rule_id"], "external-approval")

    def test_draft_pack_cannot_activate(self):
        pack = {
            "policy_pack_id": "conversation-safety-draft",
            "schema_version": "policy_pack.v1",
            "version": "0.1.0",
            "lifecycle_status": "draft",
            "rules": [{"rule_id": "external-approval", "priority": 100, "rule_text": "Do not send external messages unless approval is present."}],
        }
        activation = activate_policy_pack(pack)
        self.assertFalse(activation["ok"])
        self.assertEqual(activation["activation_state"], "not_active")

    def test_incompatible_pack_is_invalid(self):
        pack = {
            "policy_pack_id": "future-pack",
            "schema_version": "policy_pack.v9",
            "version": "9.0.0",
            "lifecycle_status": "active",
            "rules": [{"rule_id": "external-approval", "priority": 100, "rule_text": "Do not send external messages unless approval is present."}],
        }
        validation = validate_policy_pack(pack)
        self.assertFalse(validation["ok"])
        self.assertIn("unsupported_schema_version", validation["errors"])

    def test_policy_pack_lifecycle_benchmark(self):
        cases = Path("lce_validation/fixtures/policy_pack_lifecycle_cases.jsonl")
        with tempfile.TemporaryDirectory() as td:
            summary = run_policy_pack_lifecycle_benchmark(cases, Path(td) / "out")
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["case_count"], 5)
            self.assertEqual(summary["case_accuracy"], 1.0)
