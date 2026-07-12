import unittest
from lce_validation.runtime.japanese_dialogue import load_japanese_dialogue_data, respond_japanese
from lce_validation.web_ui import dispatch_response

class JapaneseDialogueTests(unittest.TestCase):
    def test_dataset_is_substantial_and_unique(self):
        rows=load_japanese_dialogue_data()
        self.assertGreaterEqual(len(rows),45)
        self.assertEqual(len(rows),len({row["id"] for row in rows}))
        self.assertTrue(all(row["patterns"] and row["response"] and row["act"] for row in rows))

    def test_core_japanese_dialogue_acts(self):
        cases=(("こんにちは","greeting"),("LCEとは何ですか","explanation"),
               ("それは違うと思います","repair"),("もう少し詳しく説明して","detailed_explanation"))
        for text,act in cases:
            with self.subTest(text=text):
                result=respond_japanese(text,[])
                self.assertEqual(act,result["dialogue_act"]); self.assertTrue(result["response"])

    def test_unknown_abstains_and_context_reference_repairs(self):
        unknown=respond_japanese("量子バナナの法則を教えて",[])
        self.assertEqual("clarification",unknown["dialogue_act"]); self.assertIsNone(unknown["evidence_id"])
        repaired=respond_japanese("それについて",[{"speaker":"user","text":"Cube構造について教えて"}])
        self.assertEqual("context_repair",repaired["dialogue_act"])

    def test_web_dispatch(self):
        result=dispatch_response({"mode":"japanese","text":"何ができるの？","history":[]})
        self.assertEqual("japanese_dialogue",result["route"]); self.assertEqual("ja",result["language_status"])

    def test_v2_metadata_and_hard_negatives(self):
        result=respond_japanese("根拠を示して",[])
        self.assertEqual("MATCH",result["match_decision"]); self.assertEqual("verification",result["topic"])
        blocked=respond_japanese("『ありがとう』という言葉とは何ですか",[])
        self.assertNotEqual("acknowledgement",blocked["dialogue_act"])
        negated=respond_japanese("疲れたわけではない",[])
        self.assertNotEqual("empathic_support",negated["dialogue_act"])
        self.assertIn("output_metadata",result)

    def test_structured_transition_is_not_json_explanation(self):
        self.assertEqual("structured_transition",respond_japanese("JSONで返して",[])["dialogue_act"])
        self.assertNotEqual("structured_transition",respond_japanese("JSONについて説明して",[])["dialogue_act"])

    def test_context_requirements_and_output_plan(self):
        missing=respond_japanese("ここまでをまとめて",[])
        self.assertNotEqual("conversation_summary",missing["dialogue_act"])
        available=respond_japanese("ここまでをまとめて",[{"speaker":"user","text":"LCEについて"}])
        self.assertEqual("conversation_summary",available["dialogue_act"])
        follow=respond_japanese("何から始める？",[])
        self.assertEqual("candidate_list",follow["output_plan"][-1]["code"])
