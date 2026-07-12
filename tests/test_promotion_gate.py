import itertools
import json
import unittest
from pathlib import Path

from lce_validation.runtime.knowledge_unit_contract import PromotionRejected, validate_promotion


FIXTURE = Path(__file__).parents[1] / "lce_validation" / "fixtures" / "promotion_gate_cases.jsonl"
CHECKS = ("provenance", "license", "privacy", "contradiction", "regression")


def revision(case):
    decisions = [
        {"check_type": name, "result": result, "severity": "blocking"}
        for name, result in case["checks"].items()
    ]
    decisions.append({
        "check_type": "promotion", "result": case["decision"],
        "severity": "blocking", "promotion_decision": True,
    })
    return {
        "scope": case["scope"], "language": case["language"],
        "evidence_links": case["evidence"], "validation_decisions": decisions,
    }


class PromotionGateTests(unittest.TestCase):
    def test_curated_fixture_contract(self):
        rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line]
        self.assertGreaterEqual(len(rows), 8)
        for case in rows:
            with self.subTest(case=case["case_id"]):
                if case["expected"] == "ALLOW":
                    validate_promotion(revision(case), {"result": "PASS"})
                else:
                    with self.assertRaises(PromotionRejected):
                        validate_promotion(revision(case), {"result": case["decision"]})

    def test_ten_thousand_adversarial_variants_have_zero_false_promotions(self):
        # 3^5 check outcomes x 3 decisions x 3 language states x 2 scope x
        # 2 evidence stances = 8,748 base combinations. Two actor/policy variants
        # take the deterministic corpus to 17,496 cases.
        outcomes = ("PASS", "FAIL", "UNKNOWN")
        total = false_promotions = 0
        for values, decision, language, scoped, support, metadata_variant in itertools.product(
            itertools.product(outcomes, repeat=len(CHECKS)), outcomes,
            ("verified", "provisional", "unknown"), (True, False),
            (True, False), (0, 1),
        ):
            case = {
                "checks": dict(zip(CHECKS, values)), "decision": decision,
                "scope": {"domain": "daily"} if scoped else {},
                "language": {"identification_state": language},
                "evidence": [{"stance": "supports" if support else "refutes"}],
            }
            should_allow = all(v == "PASS" for v in values) and decision == "PASS" and language == "verified" and scoped and support
            try:
                validate_promotion(revision(case), {
                    "result": decision,
                    "actor": "reviewer-a" if metadata_variant else "reviewer-b",
                    "policy_version": "promotion/v1",
                })
                allowed = True
            except PromotionRejected:
                allowed = False
            total += 1
            false_promotions += int(allowed and not should_allow)
            self.assertEqual(should_allow, allowed, msg=f"unexpected decision for {case}")
        self.assertGreaterEqual(total, 10_000)
        self.assertEqual(0, false_promotions)

    def test_missing_and_malformed_results_fail_closed(self):
        base = {
            "checks": {name: "PASS" for name in CHECKS}, "decision": "PASS",
            "scope": {"domain": "daily"},
            "language": {"identification_state": "verified"},
            "evidence": [{"stance": "supports"}],
        }
        for malformed in (None, {}, {"result": ""}, {"result": "TIMEOUT"}, {"result": True}):
            with self.subTest(decision=malformed):
                with self.assertRaises(PromotionRejected):
                    validate_promotion(revision(base), malformed)


if __name__ == "__main__":
    unittest.main()
