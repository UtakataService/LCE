import tempfile
import unittest
from pathlib import Path

from lce_validation.runtime.knowledge_unit import Evidence, EvidenceLink, KnowledgeUnitDraft
from lce_validation.runtime.knowledge_unit_repository import JsonKnowledgeUnitRepository, PromotionRejected


class PromotionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / "knowledge.json"
        self.repo = JsonKnowledgeUnitRepository(path, tenant_id="tenant-a")
        self.other = JsonKnowledgeUnitRepository(path, tenant_id="tenant-b")

    def tearDown(self):
        self.temp.cleanup()

    def _shadow(self):
        draft = KnowledgeUnitDraft(
            claim={"subject_ref":"concept:water","predicate_ref":"relation:is_a","object":{"concept_ref":"concept:substance"}},
            scope={"domain":"daily","language_variety":"en"},
            language={"expression_language":"en","source_language":"en","identification_state":"verified"},
        )
        row = self.repo.create_observation(draft, actor="author", idempotency_key="create")
        for status in ("QUARANTINED", "NORMALIZED", "LINKED", "VERIFIED", "SHADOW"):
            row = self.repo._call(self.repo._repo.transition, {
                "unit_id": row.logical_id, "target_status": status, "actor": "reviewer",
                "decision": {"result":"PASS"}, "expected_revision_no": row.revision_no,
                "idempotency_key": f"to-{status}",
            })
        evidence_id = f"ev-water-{self.repo.tenant_id}"
        evidence = Evidence(evidence_id, "Water is matter.", "Water is matter.", "fixture://water", "a"*64, "test-only", "en")
        self.repo.put_evidence(evidence, actor="reviewer", idempotency_key="put-evidence")
        return self.repo.attach_evidence(row.logical_id, EvidenceLink(evidence_id, "supports", "fixture"), "reviewer", row.revision_no, "attach")

    def _decision(self, result="PASS"):
        return {"actor":"approver", "result":result, "policy_version":"promotion/v1"}

    def _with_checks(self, row, altered=None):
        checks = {name:"PASS" for name in ("provenance","license","privacy","contradiction","regression")}
        if altered:
            checks.update(altered)
        patch = {"validation_decisions":[
            {"check_type":name,"result":value,"severity":"blocking"} for name,value in checks.items()
        ] + [{"check_type":"promotion","result":"PASS","severity":"blocking","promotion_decision":True}]}
        return self.repo.revise(row.logical_id, patch, "validation snapshot", "validator", row.revision_no, "checks-" + str(altered))

    def test_fail_unknown_and_missing_checks_do_not_mutate_history(self):
        for result in ("FAIL", "UNKNOWN"):
            with self.subTest(result=result):
                row = self._shadow() if result == "FAIL" else self._shadow_new("unknown")
                row = self._with_checks(row, {"privacy": result})
                before = tuple(self.repo.list_history(row.logical_id))
                with self.assertRaises(PromotionRejected):
                    self.repo.transition(row.logical_id, "ACTIVE_L1", decision=self._decision(), expected_revision_no=row.revision_no, idempotency_key=f"promote-{result}")
                after = tuple(self.repo.list_history(row.logical_id))
                self.assertEqual([x.revision_id for x in before], [x.revision_id for x in after])
                self.assertEqual("SHADOW", self.repo.get_current(row.logical_id).status)

    def _shadow_new(self, suffix):
        # Keep each workflow independent while sharing the same repository file.
        original = self.repo
        self.repo = JsonKnowledgeUnitRepository(original.path, tenant_id=f"tenant-a-{suffix}")
        return self._shadow()

    def test_cross_tenant_cannot_read_or_promote(self):
        row = self._with_checks(self._shadow())
        self.assertIsNone(self.other.get_current(row.logical_id))
        with self.assertRaises(PromotionRejected):
            self.other.transition(row.logical_id, "ACTIVE_L1", decision=self._decision(), expected_revision_no=row.revision_no, idempotency_key="cross-tenant")

    def test_stale_revision_promotion_is_rejected_without_active_head(self):
        row = self._with_checks(self._shadow())
        stale = row.revision_no
        row = self.repo.revise(row.logical_id, {"scope":{"domain":"daily","language_variety":"en","region":"global"}}, "scope update", "reviewer", row.revision_no, "scope-update")
        with self.assertRaises(Exception):
            self.repo.transition(row.logical_id, "ACTIVE_L1", decision=self._decision(), expected_revision_no=stale, idempotency_key="stale-promote")
        self.assertEqual("SHADOW", self.repo.get_current(row.logical_id).status)


if __name__ == "__main__":
    unittest.main()
