import statistics,time,unittest
from lce_validation.runtime.dialogue_completion import respond_with_completion

def turn(text,history):
    result=respond_with_completion(text,history); history.append({"speaker":"assistant","text":result["response"],"completion_state":result["completion_state"]}); return result

class DialogueCompletionTests(unittest.TestCase):
    def test_comparison_three_turn_completion(self):
        h=[]; r1=turn("どちらがいい？",h); self.assertEqual("comparison_options",r1["completion_state"]["pending_slot"])
        r2=turn("MySQLとJSON",h); self.assertEqual("priority_axis",r2["completion_state"]["pending_slot"])
        r3=turn("速度",h); self.assertEqual("COMPLETE",r3["completion_status"]); self.assertIn("MySQL",r3["response"])
    def test_comparison_targets_in_first_turn(self):
        h=[]; r1=turn("MySQLとJSONを比較して",h); self.assertEqual("priority_axis",r1["completion_state"]["pending_slot"])
        self.assertEqual("COMPLETE",turn("保守性",h)["completion_status"])
    def test_invalid_slot_does_not_complete(self):
        h=[]; turn("AとBを比較して",h); r=turn("なんとなく",h); self.assertEqual("INCOMPLETE",r["completion_status"]); self.assertGreater(r["completion_state"]["attempts"],0)
    def test_cancel_pending(self):
        h=[]; turn("どっちがいい？",h); self.assertEqual("CANCELLED",turn("やっぱり取り消し",h)["completion_status"])
    def test_deletion_scope_never_executes(self):
        h=[]; turn("保存情報を削除して",h); r=turn("このセッション",h); self.assertEqual("BLOCKED",r["completion_status"]); self.assertIn("承認",r["response"])
    def test_deletion_target_and_scope_are_unambiguous(self):
        h=[]; first=turn("削除して",h); self.assertEqual("deletion_target",first["completion_state"]["pending_slot"])
        second=turn("検索履歴",h); self.assertEqual("deletion_scope",second["completion_state"]["pending_slot"])
        ambiguous=turn("この会話とこのセッション",h); self.assertEqual("INCOMPLETE",ambiguous["completion_status"])
        final=turn("この会話ではなくこのセッション",h); self.assertEqual("このセッション",final["completion_state"]["deletion_scope"])
    def test_cpu_latency_1000_turns(self):
        values=[respond_with_completion("LCEとは何ですか",[])["latency_ms"] for _ in range(1000)]
        p95=statistics.quantiles(values,n=20)[18]
        self.assertLess(p95,30.0)

if __name__=="__main__":unittest.main()
