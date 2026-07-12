import json
import tempfile
import unittest
from pathlib import Path

from lce_validation.runtime.knowledge_unit_migration import (
    MigrationVerificationError, backfill_json_to_mysql, canonical_hash,
    dual_read_verify, load_checkpoint, source_fingerprint,
)


class MemoryTarget:
    def __init__(self, fail_on=None):
        self.rows = {}
        self.calls = 0
        self.fail_on = fail_on

    def import_record(self, record, *, idempotency_key):
        self.calls += 1
        if self.calls == self.fail_on:
            raise ConnectionError("injected database outage")
        self.rows[idempotency_key] = dict(record)

    def export_record(self, logical_id, revision):
        return self.rows[f"{logical_id}:{revision}"]


class KnowledgeUnitMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.rows = [
            {"logical_id": "ku-1", "revision_no": 1, "status": "OBSERVED", "text": "Xin chào"},
            {"logical_id": "ku-1", "revision_no": 2, "status": "VERIFIED", "text": "こんにちは"},
        ]
        self.source = self.root / "source.json"
        self.source.write_text(json.dumps(self.rows, ensure_ascii=False), encoding="utf-8")
        self.checkpoint = self.root / "checkpoint.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_idempotent_migration_preserves_unicode_and_revision_history(self):
        target = MemoryTarget()
        first = backfill_json_to_mysql(self.source, target, checkpoint_path=self.checkpoint)
        second = backfill_json_to_mysql(self.source, target, checkpoint_path=self.checkpoint)
        self.assertEqual((first.imported, first.verified), (2, 2))
        self.assertEqual(second.imported, 0)
        self.assertEqual(set(target.rows), {"ku-1:1", "ku-1:2"})
        self.assertEqual(target.rows["ku-1:1"]["text"], "Xin chào")
        self.assertEqual(target.rows["ku-1:2"]["text"], "こんにちは")

    def test_canonical_mismatch_blocks_verification(self):
        target = MemoryTarget()
        target.rows["ku-1:1"] = {**self.rows[0], "text": "tampered"}
        target.rows["ku-1:2"] = self.rows[1]
        result = dual_read_verify(self.source, target)
        self.assertFalse(result["ok"])
        self.assertEqual(result["matched"], 1)

    def test_failure_checkpoint_resumes_without_duplicate_revision(self):
        failing = MemoryTarget(fail_on=2)
        with self.assertRaises(ConnectionError):
            backfill_json_to_mysql(self.source, failing, checkpoint_path=self.checkpoint)
        checkpoint = load_checkpoint(self.checkpoint, expected_source=source_fingerprint(self.source))
        self.assertEqual((checkpoint.imported, checkpoint.last_key), (1, "ku-1:1"))
        recovered = MemoryTarget()
        recovered.rows.update(failing.rows)
        result = backfill_json_to_mysql(self.source, recovered, checkpoint_path=self.checkpoint)
        self.assertEqual(result.imported, 1)
        self.assertEqual(set(recovered.rows), {"ku-1:1", "ku-1:2"})

    def test_database_failure_has_no_fallback_write_surface(self):
        self.assertNotIn("fallback", backfill_json_to_mysql.__code__.co_varnames)
        with self.assertRaises(ConnectionError):
            backfill_json_to_mysql(self.source, MemoryTarget(fail_on=1), checkpoint_path=self.checkpoint)

    def test_canonical_hash_is_stable_and_unicode_sensitive(self):
        self.assertEqual(canonical_hash(self.rows[0]), canonical_hash(dict(reversed(list(self.rows[0].items())))))
        self.assertNotEqual(canonical_hash(self.rows[0]), canonical_hash({**self.rows[0], "text": "Xin chao"}))


if __name__ == "__main__":
    unittest.main()
