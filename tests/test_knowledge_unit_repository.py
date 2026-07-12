import tempfile
import unittest
from pathlib import Path


class KnowledgeUnitRepositoryContractTests(unittest.TestCase):
    def setUp(self):
        from lce_validation.runtime.knowledge_unit import Evidence, EvidenceLink, KnowledgeUnitDraft
        from lce_validation.runtime.knowledge_unit_repository import (
            ConcurrencyConflict,
            EvidenceNotFound,
            JsonKnowledgeUnitRepository,
            PromotionRejected,
            RepositoryUnavailable,
        )

        self.Evidence = Evidence
        self.EvidenceLink = EvidenceLink
        self.KnowledgeUnitDraft = KnowledgeUnitDraft
        self.ConcurrencyConflict = ConcurrencyConflict
        self.EvidenceNotFound = EvidenceNotFound
        self.PromotionRejected = PromotionRejected
        self.RepositoryUnavailable = RepositoryUnavailable
        self.temp = tempfile.TemporaryDirectory()
        self.repo = JsonKnowledgeUnitRepository(Path(self.temp.name) / "knowledge.json")

    def tearDown(self):
        self.temp.cleanup()

    def draft(self, value="water"):
        return self.KnowledgeUnitDraft(
            claim={
                "subject_ref": f"concept:{value}",
                "predicate_ref": "relation:is_a",
                "object": {"concept_ref": "concept:substance"},
                "polarity": "positive",
                "modality": "asserted",
            },
            scope={"domain": "daily", "language_variety": "en"},
            language={
                "expression_language": "en",
                "source_language": "en",
                "identification_state": "verified",
            },
        )

    def evidence(self, evidence_id="ev-1"):
        return self.Evidence(
            evidence_id=evidence_id,
            raw_text="Water is a substance. 水は物質です。",
            normalized_text="Water is a substance. 水は物質です。",
            source_uri="fixture://water",
            content_hash="a" * 64,
            license="test-only",
            language="en",
        )

    def test_three_revisions_are_preserved_and_head_moves(self):
        first = self.repo.create_observation(self.draft(), actor="tester", idempotency_key="create-1")
        second = self.repo.revise(
            first.logical_id,
            {"claim": {**first.claim, "modality": "reported"}},
            reason="source wording",
            actor="tester",
            expected_revision_no=1,
            idempotency_key="rev-2",
        )
        third = self.repo.revise(
            first.logical_id,
            {"scope": {"domain": "science", "language_variety": "en"}},
            reason="narrow scope",
            actor="tester",
            expected_revision_no=2,
            idempotency_key="rev-3",
        )
        history = self.repo.list_history(first.logical_id)
        self.assertEqual([row.revision_no for row in history], [1, 2, 3])
        self.assertEqual(self.repo.get_current(first.logical_id).revision_id, third.revision_id)
        self.assertEqual(self.repo.get_revision(first.revision_id).claim["modality"], "asserted")
        self.assertNotEqual(first.revision_id, second.revision_id)

    def test_stale_expected_revision_cannot_create_lost_update(self):
        first = self.repo.create_observation(self.draft(), actor="tester", idempotency_key="create-1")
        self.repo.revise(first.logical_id, {}, "one", "tester", 1, "rev-one")
        with self.assertRaises(self.ConcurrencyConflict):
            self.repo.revise(first.logical_id, {}, "stale", "tester", 1, "rev-stale")
        self.assertEqual(len(self.repo.list_history(first.logical_id)), 2)

    def test_evidence_link_must_reference_existing_evidence_and_revision(self):
        first = self.repo.create_observation(self.draft(), actor="tester", idempotency_key="create-1")
        link = self.EvidenceLink("missing", "supports", "source-a")
        with self.assertRaises(self.EvidenceNotFound):
            self.repo.attach_evidence(first.logical_id, link, "tester", 1, "link-missing")
        self.repo.put_evidence(self.evidence(), actor="tester", idempotency_key="evidence-1")
        linked = self.repo.attach_evidence(
            first.logical_id,
            self.EvidenceLink("ev-1", "supports", "source-a"),
            actor="tester",
            expected_revision_no=1,
            idempotency_key="link-1",
        )
        self.assertEqual(linked.evidence_links[0].evidence_id, "ev-1")
        self.assertEqual(self.repo.get_revision(linked.revision_id).revision_id, linked.revision_id)

    def test_generic_save_or_status_mutation_is_not_exposed(self):
        self.assertFalse(hasattr(self.repo, "save"))
        self.assertFalse(hasattr(self.repo, "set_status"))

    def test_promotion_without_all_hard_gates_is_rejected_and_not_persisted(self):
        first = self.repo.create_observation(self.draft(), actor="tester", idempotency_key="create-1")
        before = len(self.repo.list_history(first.logical_id))
        with self.assertRaises(self.PromotionRejected):
            self.repo.transition(
                first.logical_id,
                "ACTIVE_L1",
                decision={"actor": "tester", "checks": {"provenance": True}},
                expected_revision_no=1,
                idempotency_key="bad-promotion",
            )
        self.assertEqual(len(self.repo.list_history(first.logical_id)), before)
        self.assertNotEqual(self.repo.get_current(first.logical_id).status, "ACTIVE_L1")

    def test_retracted_revision_cannot_be_reactivated(self):
        first = self.repo.create_observation(self.draft(), actor="tester", idempotency_key="create-1")
        retracted = self.repo.retract(first.logical_id, "bad source", "tester", 1, "retract-1")
        with self.assertRaises((self.PromotionRejected, ValueError)):
            self.repo.transition(
                first.logical_id,
                "ACTIVE_L1",
                decision={"actor": "tester", "checks": {}},
                expected_revision_no=retracted.revision_no,
                idempotency_key="reactivate",
            )

    def test_write_failure_is_atomic(self):
        from unittest.mock import patch

        with patch("os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(self.RepositoryUnavailable):
                self.repo.create_observation(self.draft(), actor="tester", idempotency_key="create-1")
        self.assertEqual(self.repo.count(), 0)


if __name__ == "__main__":
    unittest.main()
