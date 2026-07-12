import unittest

from lce_validation.runtime.layered_reasoning import run_layered_reasoning,stable_view
from lce_validation.web_ui import dispatch_response


class LayeredReasoningTests(unittest.TestCase):
    def test_explicit_ab_issues_are_isolated(self):
        result=run_layered_reasoning("Aについて速度を比較して、Bについて安全性を深く検証して")
        self.assertEqual(2,result["issue_count"])
        self.assertEqual(["A","B"],[item["label"] for item in result["issues"]])
        self.assertNotEqual(result["lanes"][0]["isolated_input_hash"],result["lanes"][1]["isolated_input_hash"])
        self.assertFalse(result["integration"]["cross_issue_leakage"])

    def test_depth_is_selected_per_issue(self):
        result=run_layered_reasoning("unused",issues=[{"label":"A","text":"要点を答えて"},{"label":"B","text":"安全性と矛盾を深く厳密に監査して"}])
        self.assertEqual("D1",result["issues"][0]["depth"])
        self.assertIn(result["issues"][1]["depth"],{"D3","D4"})

    def test_parallel_and_sequential_have_same_stable_result(self):
        issues=[{"label":"A","text":"速度を比較して"},{"label":"B","text":"精度を比較して"}]
        sequential=run_layered_reasoning("compare",issues=issues,parallel=False)
        parallel=run_layered_reasoning("compare",issues=issues,parallel=True)
        self.assertEqual(stable_view(sequential),stable_view(parallel))

    def test_partial_does_not_erase_other_lane(self):
        issues=[{"label":"A","text":"JSONで返して"},{"label":"B","text":"短く要点を答えて","required":False}]
        result=run_layered_reasoning("mixed",issues=issues)
        self.assertEqual(2,len(result["lanes"]))
        self.assertEqual(["issue-01","issue-02"],result["integration"]["ordered_issue_ids"])

    def test_issue_count_is_bounded(self):
        issues=[{"label":str(i),"text":f"question {i}"} for i in range(20)]
        result=run_layered_reasoning("many",issues=issues,parallel=True)
        self.assertEqual(8,result["issue_count"])
        self.assertEqual("sequential_budget_fallback",result["execution_mode"])

    def test_web_dispatch_accepts_explicit_issues(self):
        result=dispatch_response({"mode":"layered_reasoning","text":"A and B","parallel":True,"issues":[{"label":"A","text":"Explain A"},{"label":"B","text":"Explain B"}]})
        self.assertEqual("layered_reasoning",result["route"])
        self.assertEqual("parallel",result["execution_mode"])


if __name__=="__main__":unittest.main()
