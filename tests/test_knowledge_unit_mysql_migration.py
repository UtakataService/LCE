import json
import tempfile
import unittest
from pathlib import Path

from lce_validation.runtime.knowledge_unit_migration import (
    MigrationConflictError, backfill_json_to_mysql, dual_read_verify,
    export_rollback_snapshot, load_checkpoint, source_fingerprint,
    verify_rollback_snapshot,
)


class TenantTarget:
    def __init__(self):
        self.rows = {}

    def import_record(self, record, *, idempotency_key):
        self.rows[idempotency_key] = dict(record)

    def export_record(self, logical_id, revision, *, tenant_id=None):
        matches = [v for v in self.rows.values() if v["logical_id"] == logical_id and v["revision_no"] == revision
                   and (tenant_id is None or v["tenant_id"] == tenant_id)]
        if len(matches) != 1:
            raise KeyError((logical_id, revision))
        return matches[0]

    def iter_export_records(self, *, after_key=None, tenant_id=None, batch_size=100):
        rows = sorted(self.rows.values(), key=lambda r: (r["tenant_id"], r["logical_id"], r["revision_no"]))
        return [r for r in rows if tenant_id is None or r["tenant_id"] == tenant_id]


class MySQLMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.json"
        self.rows = [{"logical_id": f"ku-{i}", "revision_no": 1, "text": "Xin chào"} for i in range(5)]
        self.source.write_text(json.dumps(self.rows, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_tenant_is_in_record_idempotency_key_and_parity(self):
        target = TenantTarget()
        result = backfill_json_to_mysql(self.source, target, checkpoint_path=self.root / "cp.json",
                                        tenant_id="tenant-a", batch_size=2)
        self.assertEqual((result.imported, result.verified, result.batches), (5, 5, 3))
        self.assertTrue(all(key.startswith("tenant-a:") for key in target.rows))
        self.assertTrue(all(row["tenant_id"] == "tenant-a" for row in target.rows.values()))
        self.assertTrue(dual_read_verify(self.source, target, tenant_id="tenant-a")["ok"])

    def test_embedded_cross_tenant_record_is_rejected(self):
        self.source.write_text(json.dumps([{**self.rows[0], "tenant_id": "tenant-b"}]), encoding="utf-8")
        with self.assertRaises(MigrationConflictError):
            backfill_json_to_mysql(self.source, TenantTarget(), checkpoint_path=self.root / "cp.json",
                                   tenant_id="tenant-a")

    def test_checkpoint_is_bound_to_tenant(self):
        target = TenantTarget()
        checkpoint = self.root / "cp.json"
        backfill_json_to_mysql(self.source, target, checkpoint_path=checkpoint, tenant_id="tenant-a")
        with self.assertRaises(MigrationConflictError):
            backfill_json_to_mysql(self.source, target, checkpoint_path=checkpoint, tenant_id="tenant-b")

    def test_rollback_snapshot_is_tenant_scoped_and_verifiable(self):
        target = TenantTarget()
        for tenant in ("tenant-a", "tenant-b"):
            backfill_json_to_mysql(self.source, target, checkpoint_path=self.root / f"{tenant}.json", tenant_id=tenant)
        destination = self.root / "rollback.jsonl"
        manifest = export_rollback_snapshot(target, destination, tenant_id="tenant-a", batch_size=2)
        self.assertEqual(manifest["record_count"], 5)
        self.assertEqual(manifest["tenant_id"], "tenant-a")
        self.assertTrue(verify_rollback_snapshot(destination)["ok"])
        rows = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({row["tenant_id"] for row in rows}, {"tenant-a"})

    def test_performance_metrics_use_injected_monotonic_clock(self):
        ticks = iter((10.0, 12.0))
        result = backfill_json_to_mysql(self.source, TenantTarget(), checkpoint_path=self.root / "cp.json",
                                        tenant_id="tenant-a", clock=lambda: next(ticks))
        self.assertEqual(result.elapsed_seconds, 2.0)
        self.assertEqual(result.records_per_second, 2.5)


if __name__ == "__main__":
    unittest.main()
