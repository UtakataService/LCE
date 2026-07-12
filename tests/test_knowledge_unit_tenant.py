import tempfile
import unittest
from pathlib import Path


class KnowledgeUnitTenantAndPromotionTests(unittest.TestCase):
    def setUp(self):
        from lce_validation.runtime.knowledge_unit import Evidence, EvidenceLink, KnowledgeUnitDraft
        from lce_validation.runtime.knowledge_unit_repository import JsonKnowledgeUnitRepository, PromotionRejected

        self.Evidence = Evidence
        self.EvidenceLink = EvidenceLink
        self.KnowledgeUnitDraft = KnowledgeUnitDraft
        self.PromotionRejected = PromotionRejected
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / "shared.json"
        self.tenant_a = JsonKnowledgeUnitRepository(path, tenant_id="tenant-a")
        self.tenant_b = JsonKnowledgeUnitRepository(path, tenant_id="tenant-b")

    def tearDown(self):
        self.temp.cleanup()

    def draft(self, value="water"):
        return self.KnowledgeUnitDraft(
            claim={"subject_ref": f"concept:{value}", "predicate_ref": "relation:is_a", "object": {"concept_ref": "concept:substance"}},
            scope={"domain": "daily", "language_variety": "en"},
            language={"expression_language": "en", "source_language": "en", "identification_state": "verified"},
        )

    def test_cross_tenant_read_history_and_revision_are_denied(self):
        row = self.tenant_a.create_observation(self.draft(), actor="tester", idempotency_key="create")
        self.assertIsNone(self.tenant_b.get_current(row.logical_id))
        self.assertEqual((), self.tenant_b.list_history(row.logical_id))
        with self.assertRaises(Exception):
            self.tenant_b.get_revision(row.revision_id)

    def test_idempotency_namespace_is_tenant_local(self):
        first = self.tenant_a.create_observation(self.draft("water"), actor="tester", idempotency_key="shared")
        second = self.tenant_b.create_observation(self.draft("fire"), actor="tester", idempotency_key="shared")
        self.assertNotEqual(first.logical_id, second.logical_id)
        self.assertEqual("tenant-a", first.tenant_id)
        self.assertEqual("tenant-b", second.tenant_id)

    def test_fail_and_unknown_promotion_decisions_are_rejected_without_mutation(self):
        for result in ("FAIL", "UNKNOWN"):
            with self.subTest(result=result):
                repo = self.tenant_a
                row = repo.create_observation(self.draft(result.lower()), actor="tester", idempotency_key=f"create-{result}")
                row = self._advance_to_shadow(repo, row)
                before = tuple(repo.list_history(row.logical_id))
                decision = {
                    "actor": "validator",
                    "result": result,
                    "promotion_decision": True,
                    "checks": {name: "PASS" for name in ("provenance", "license", "privacy", "contradiction", "regression")},
                }
                with self.assertRaises(self.PromotionRejected):
                    repo._call(repo._repo.transition, {
                        "tenant_id": repo.tenant_id,
                        "unit_id": str(row.logical_id),
                        "target_status": "ACTIVE_L1",
                        "actor": "validator",
                        "decision": decision,
                        "validation_decisions": list(decision["checks"].items()),
                        "expected_revision_no": row.revision_no,
                        "idempotency_key": f"promote-{result}",
                    })
                after = tuple(repo.list_history(row.logical_id))
                self.assertEqual([item.revision_id for item in before], [item.revision_id for item in after])
                self.assertEqual("SHADOW", repo.get_current(row.logical_id).status)

    def _advance_to_shadow(self, repo, row):
        for status in ("QUARANTINED", "NORMALIZED", "LINKED", "VERIFIED", "SHADOW"):
            row = repo._call(repo._repo.transition, {
                "tenant_id": repo.tenant_id,
                "unit_id": str(row.logical_id),
                "target_status": status,
                "actor": "tester",
                "decision": {"actor": "tester", "result": "PASS"},
                "expected_revision_no": row.revision_no,
                "idempotency_key": f"to-{row.logical_id}-{status}",
            })
        evidence = self.Evidence(
            evidence_id=f"ev-{row.logical_id}", raw_text="Water is matter.", normalized_text="Water is matter.",
            source_uri="fixture://tenant", content_hash="a" * 64, license="test-only", language="en",
        )
        repo.put_evidence(evidence, actor="tester", idempotency_key=f"put-{row.logical_id}")
        return repo.attach_evidence(
            row.logical_id, self.EvidenceLink(evidence.evidence_id, "supports", "fixture"), "tester",
            row.revision_no, f"attach-{row.logical_id}",
        )


if __name__ == "__main__":
    unittest.main()
