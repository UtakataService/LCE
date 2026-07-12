import json,unittest
from pathlib import Path
from lce_validation.runtime.hypothesis_loop import run_hypothesis_loop
from lce_validation.runtime.data_quality import DataQualityEvaluator,RawEvidence

class LearningDataV2Tests(unittest.TestCase):
    def test_episode_manifest_contract_and_splits(self):
        rows=[json.loads(x) for x in Path("lce_validation/fixtures/learning_data_v2_r2_episodes.jsonl").read_text(encoding="utf-8").splitlines() if x]
        self.assertEqual(20,len(rows)); self.assertEqual(20,len({r["episode_id"] for r in rows}))
        self.assertEqual({"shadow_train","interaction_blind","final_holdout"},{r["split"] for r in rows})
        self.assertTrue(all({"family","turns","expected","slot_gold","verifier","repair","split"}<=r.keys() for r in rows))
    def test_hvr_rejects_three_comparison_targets(self):
        r=run_hypothesis_loop("MySQLとJSONとSQLiteを比較して",[])
        self.assertEqual("CLARIFY",r["decision"])
    def test_hvr_rejects_multiple_axes(self):
        history=[{"speaker":"assistant","completion_state":{"revision":1,"goal":"compare","status":"PENDING","options":["A","B"],"priority_axis":None,"deletion_target":None,"deletion_scope":None,"schema_fields":[],"pending_slot":"priority_axis","attempts":0,"slot_status":"PENDING","question_revision":1,"expires_revision":5,"parent_state_hash":None,"policy_version":"dialogue-completion-v1"}}]
        r=run_hypothesis_loop("速度と精度",history)
        self.assertEqual("CLARIFY",r["decision"]); self.assertEqual("comparison",r["domain"])
    def test_unknown_dialogue_does_not_accept(self):
        self.assertNotEqual("ACCEPT",run_hypothesis_loop("何の話？",[])["decision"])
    def test_json_entity_is_not_structured_without_output_cue(self):
        self.assertNotEqual("structured",run_hypothesis_loop("JSONとMySQLを比較して",[])["domain"])
    def test_evidence_negation_is_not_evidence_request(self):
        self.assertNotEqual("evidence",run_hypothesis_loop("根拠は不要です",[])["domain"])
    def test_structured_clarification_has_text(self):
        r=run_hypothesis_loop("JSON形式で出力して",[],data={},schema=None)
        self.assertEqual("CLARIFY",r["decision"]); self.assertTrue(r["response"])
    def test_null_completion_state_history_is_safe(self):
        run_hypothesis_loop("続けて",[{"completion_state":None}])
    def test_round3_episode_quality_and_lineage_contract(self):
        rows=[json.loads(x) for x in Path("lce_validation/fixtures/learning_data_v2_r3_episodes.jsonl").read_text(encoding="utf-8").splitlines() if x]
        self.assertEqual(24,len(rows)); self.assertEqual(24,len({r["lineage_id"] for r in rows}))
        train={r["source_family"] for r in rows if r["split"]=="shadow_train"}; blind={r["source_family"] for r in rows if r["split"]=="interaction_blind"}
        self.assertFalse(train & blind)
        for row in rows:
            text=" ".join(row["turns"])+" 学習データ評価用の会話エピソードです。"
            report=DataQualityEvaluator().evaluate(RawEvidence(row["episode_id"],text,"https://example.org/internal/"+row["lineage_id"],row["license"],row["language"],row["consent"],row["source_family"]))
            self.assertTrue(report.candidate_eligible,msg=(row["episode_id"],report.reason_codes))
    def test_unknown_named_concept_is_not_false_accept(self):
        self.assertNotEqual("ACCEPT",run_hypothesis_loop("火星寿司プロトコルについて教えて",[])["decision"])
if __name__=="__main__":unittest.main()
