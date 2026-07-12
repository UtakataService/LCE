import unittest
import json
from pathlib import Path
from lce_validation.runtime.dialogue_state import parse_utterance,respond_with_dialogue_state

class DialogueStateTests(unittest.TestCase):
    def test_round3_fixed_24_contract(self):
        path=Path("lce_validation/fixtures/dialogue_state_r3_fixed.jsonl")
        rows=[json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
        self.assertEqual(24,len(rows))
        for case in rows:
            with self.subTest(case=case["id"]):
                result=respond_with_dialogue_state(case["text"],case["history"])
                kinds=[x["kind"] for x in result["output_chunks"]]
                self.assertEqual(case["decision"],result["decision"])
                if case.get("required_kind"): self.assertIn(case["required_kind"],kinds)
                if case.get("forbidden_kind"): self.assertNotIn(case["forbidden_kind"],kinds)
                if case.get("required_intent"): self.assertIn(case["required_intent"],result["intent_chain"])
                if case.get("forbidden_intent"): self.assertNotIn(case["forbidden_intent"],result["intent_chain"])
    def test_negated_json_is_not_executed(self):
        r=respond_with_dialogue_state("JSONでは返さないで",[{"speaker":"assistant","schema":{"type":"object"}}])
        self.assertNotIn("request_structured_output",r["intent_chain"]); self.assertNotIn("structured_output",[x["kind"] for x in r["output_chunks"]])

    def test_negated_delete_and_evidence_are_not_action_intents(self):
        delete=respond_with_dialogue_state("忘れてほしいわけではありません",[])
        evidence=respond_with_dialogue_state("根拠の提示依頼ではありません",[])
        self.assertNotIn("delete_data",delete["intent_chain"]["intents"])
        self.assertNotIn("request_evidence",evidence["intent_chain"]["intents"])
        stopped=respond_with_dialogue_state("JSONで出すのはやめて",[])
        self.assertNotIn("request_structured_output",stopped["intent_chain"]["intents"])
        self.assertEqual("negation_acknowledgement",stopped["output_chunks"][0]["kind"])
    def test_quoted_directive_is_not_executed(self):
        r=respond_with_dialogue_state("『JSONで返して』という表現を説明して",[])
        self.assertIn("QUOTED_DIRECTIVE_NOT_EXECUTED",r["reason_trace"])
        self.assertNotIn("structured_output",[x["kind"] for x in r["output_chunks"]])
    def test_unresolved_reference_clarifies(self):
        r=respond_with_dialogue_state("それについて",[]); self.assertEqual("CLARIFY",r["decision"])
    def test_reference_with_history_applies(self):
        r=respond_with_dialogue_state("それについて詳しく教えて",[{"speaker":"user","text":"Cube構造について"}])
        self.assertEqual("APPLY",r["decision"])
    def test_compound_intent_preserves_order(self):
        r=respond_with_dialogue_state("短く説明して、根拠も示して",[])
        self.assertEqual(["make_concise","request_evidence","request_explanation"],r["intent_chain"])
        self.assertEqual(["style","evidence","answer"],[x["kind"] for x in r["output_chunks"]])
    def test_schema_required_before_structured_output(self):
        r=respond_with_dialogue_state("説明して、そのあとJSONで返して",[])
        self.assertEqual("CLARIFY",r["decision"]); self.assertEqual("SCHEMA_REQUIRED",r["output_chunks"][0]["code"])
    def test_schema_history_enables_structured_plan(self):
        r=respond_with_dialogue_state("同じ形式でJSONで返して",[{"speaker":"assistant","schema":{"type":"object"}}])
        self.assertIn("structured_output",[x["kind"] for x in r["output_chunks"]])
    def test_state_hash_changes_after_apply(self):
        r=respond_with_dialogue_state("LCEについて詳しく教えて",[])
        self.assertNotEqual(r["state_hash_before"],r["state_hash_after"])

if __name__=="__main__": unittest.main()
