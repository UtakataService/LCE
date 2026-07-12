import unittest
from lce_validation.runtime.data_quality import RawEvidence
from lce_validation.runtime.high_quality_pilot import PilotRow, ShadowKnowledgePilot, benchmark

def row(i,lang,q,a,topic="facts"):
    return PilotRow(RawEvidence(i,a,"https://example.org/"+i,"CC-BY-4.0",lang,True),q,a,topic)

class PilotTests(unittest.TestCase):
    def test_quality_gated_pre_post_and_unknown_abstention(self):
        cases=[("en","At what temperature does water freeze?","Water freezes at zero degrees Celsius."),
               ("ja","日本の首都はどこですか？","日本の首都は東京です。"),
               ("en","Who invented the fictional flux spoon?",None)]
        engine=ShadowKnowledgePilot(); pre=benchmark(engine,cases)
        accepted,rejected=engine.ingest([row("en-1","en",cases[0][1],cases[0][2]),row("ja-1","ja",cases[1][1],cases[1][2]),
            row("bad","en","Leaked credential?","api_key=secret")])
        post=benchmark(engine,cases)
        self.assertEqual((2,1),(len(accepted),len(rejected)))
        self.assertEqual(1,pre["correct"]); self.assertEqual(3,post["correct"])
        self.assertTrue(engine.answer(cases[2][1])["abstained"])
    def test_failed_quality_never_enters_shadow(self):
        engine=ShadowKnowledgePilot(); accepted,rejected=engine.ingest([row("x","und","unknown words here","answer")])
        self.assertFalse(accepted); self.assertEqual(1,len(rejected)); self.assertTrue(engine.answer("unknown words here")["abstained"])
