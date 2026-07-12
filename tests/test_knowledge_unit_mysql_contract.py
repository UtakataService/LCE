import os
import tempfile
import unittest
from pathlib import Path


def _mysql_environment():
    required = ("LCE_MYSQL_HOST", "LCE_MYSQL_USER", "LCE_MYSQL_PASSWORD", "LCE_MYSQL_DATABASE")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise unittest.SkipTest("real MySQL contract disabled; missing " + ", ".join(missing))
    try:
        import pymysql
    except ImportError as exc:
        raise unittest.SkipTest("real MySQL contract disabled; pymysql is not installed") from exc

    def connect():
        return pymysql.connect(
            host=os.environ["LCE_MYSQL_HOST"],
            port=int(os.environ.get("LCE_MYSQL_PORT", "3306")),
            user=os.environ["LCE_MYSQL_USER"],
            password=os.environ["LCE_MYSQL_PASSWORD"],
            database=os.environ["LCE_MYSQL_DATABASE"],
            charset="utf8mb4",
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )

    return connect


class _ContractScenario:
    backend = ""

    def make_repository(self, tenant_id):
        raise NotImplementedError

    @staticmethod
    def draft(value="water"):
        from lce_validation.runtime.knowledge_unit import KnowledgeUnitDraft

        return KnowledgeUnitDraft(
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

    def test_create_replay_is_idempotent(self):
        repo = self.make_repository("tenant-contract-a")
        first = repo.create_observation(self.draft(), actor="contract", idempotency_key="create-replay")
        replay = repo.create_observation(self.draft(), actor="contract", idempotency_key="create-replay")
        self.assertEqual(first.logical_id, replay.logical_id)
        self.assertEqual(first.revision_id, replay.revision_id)
        self.assertEqual(1, len(repo.list_history(first.logical_id)))

    def test_same_idempotency_key_with_different_command_is_rejected_atomically(self):
        repo = self.make_repository("tenant-contract-b")
        first = repo.create_observation(self.draft("water"), actor="contract", idempotency_key="same-key")
        with self.assertRaises(Exception):
            repo.create_observation(self.draft("fire"), actor="contract", idempotency_key="same-key")
        current = repo.get_current(first.logical_id)
        self.assertEqual(first.revision_id, current.revision_id)
        self.assertEqual(1, len(repo.list_history(first.logical_id)))

    def test_stale_write_is_atomic(self):
        from lce_validation.runtime.knowledge_unit_repository import ConcurrencyConflict

        repo = self.make_repository("tenant-contract-c")
        first = repo.create_observation(self.draft(), actor="contract", idempotency_key="atomic-create")
        second = repo.revise(first.logical_id, {}, "valid", "contract", 1, "atomic-valid")
        with self.assertRaises(ConcurrencyConflict):
            repo.revise(first.logical_id, {"scope": {"domain": "wrong"}}, "stale", "contract", 1, "atomic-stale")
        self.assertEqual(second.revision_id, repo.get_current(first.logical_id).revision_id)
        self.assertEqual(2, len(repo.list_history(first.logical_id)))

    def test_promote_is_atomic_and_requires_supporting_evidence(self):
        from lce_validation.runtime.knowledge_unit import Evidence, EvidenceLink
        repo = self.make_repository("tenant-contract-promote")
        row = repo.create_observation(self.draft("promotion"), actor="submitter", idempotency_key="promote-create")
        for status in ("QUARANTINED", "NORMALIZED", "LINKED", "VERIFIED", "SHADOW"):
            row = repo.transition(row.logical_id, status, decision={"actor":"reviewer", "result":"PASS"}, expected_revision_no=row.revision_no, idempotency_key="to-"+status)
        decision={"actor":"approver", "policy_version":"v1", "result":"PASS", "promotion_decision":True, "checks":{name:True for name in ("provenance","license","privacy","contradiction","regression")}}
        with self.assertRaises(Exception):
            repo.promote(row.logical_id, decision=decision, actor="approver", expected_revision_no=row.revision_no, idempotency_key="promote-no-evidence")
        ev=Evidence("ev-promote","Water is matter","Water is matter","fixture://promotion","b"*64,"test-only","en")
        repo.put_evidence(ev,actor="reviewer",idempotency_key="put-promote")
        row=repo.attach_evidence(row.logical_id,EvidenceLink("ev-promote","supports","fixture"),"reviewer",row.revision_no,"attach-promote")
        active=repo.promote(row.logical_id,decision=decision,actor="approver",expected_revision_no=row.revision_no,idempotency_key="promote-ok")
        self.assertEqual("ACTIVE_L1",active.status)


class JSONKnowledgeUnitParameterizedContract(_ContractScenario, unittest.TestCase):
    backend = "json"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "knowledge.json"

    def tearDown(self):
        self.temp.cleanup()

    def make_repository(self, tenant_id):
        from lce_validation.runtime.knowledge_unit_repository import JsonKnowledgeUnitRepository

        return JsonKnowledgeUnitRepository(self.path, tenant_id=tenant_id)


@unittest.skipUnless(os.environ.get("LCE_RUN_MYSQL_CONTRACT") == "1", "set LCE_RUN_MYSQL_CONTRACT=1 for real DB tests")
class MySQLKnowledgeUnitParameterizedContract(_ContractScenario, unittest.TestCase):
    backend = "mysql"

    def setUp(self):
        # The adapter is deliberately required here. A direct legacy repository is
        # not accepted as contract-compatible because it lacks tenant-bound APIs.
        _mysql_environment()
        try:
            from lce_validation.runtime.knowledge_unit_repository import MySQLKnowledgeUnitRepositoryAdapter
        except ImportError as exc:
            raise unittest.SkipTest("MySQL contract adapter is not implemented") from exc
        self.adapter = MySQLKnowledgeUnitRepositoryAdapter

    def make_repository(self, tenant_id):
        return self.adapter(_mysql_environment(), tenant_id=tenant_id)


if __name__ == "__main__":
    unittest.main()
