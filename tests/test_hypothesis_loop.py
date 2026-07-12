import unittest
from lce_validation.runtime.hypothesis_loop import run_hypothesis_loop

class HypothesisLoopTests(unittest.TestCase):
    def test_evidence_without_support_abstains(self):
        r=run_hypothesis_loop("その根拠を示して",[]); self.assertEqual("ABSTAIN",r["decision"]); self.assertIn("根拠",r["response"])
    def test_structured_valid_accepts(self):
        schema={"type":"object","properties":{"name":{"type":"string"}},"required":["name"],"additionalProperties":False}
        r=run_hypothesis_loop("JSONで返して",[],data={"name":"山田"},schema=schema); self.assertEqual("ACCEPT",r["decision"])
    def test_structured_invalid_clarifies(self):
        r=run_hypothesis_loop("JSONで返して",[],data={},schema=None); self.assertEqual("CLARIFY",r["decision"])
    def test_comparison_missing_slots_clarifies(self):
        r=run_hypothesis_loop("どちらがいい？",[]); self.assertEqual("CLARIFY",r["decision"])
    def test_seed_is_deterministic(self):
        a=run_hypothesis_loop("根拠は？",[]); b=run_hypothesis_loop("根拠は？",[]); self.assertEqual(a["selected_seed"],b["selected_seed"])
    def test_budget_and_revision_are_bounded(self):
        r=run_hypothesis_loop("根拠は？",[],max_revisions=99,time_budget_ms=10); self.assertLessEqual(r["revisions"],12); self.assertLess(r["latency_ms"],50)
if __name__=="__main__":unittest.main()
