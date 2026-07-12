from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lce_validation.runtime.language_overlay_store import (
    LanguageOverlayStore,
    OverlayConflictError,
    OverlayStoreError,
)


class LanguageOverlayStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LanguageOverlayStore(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_unicode_round_trip_and_version_conflict(self) -> None:
        overlay = self.store.create("vi-session", session_id="vi-session", source_language="vi")
        overlay["metadata"]["runtime_snapshot"] = {"surface": "Xin chào", "meaning": "hello"}
        saved = self.store.save(overlay, expected_version=0)
        self.assertEqual(self.store.load("vi-session")["metadata"]["runtime_snapshot"]["surface"], "Xin chào")
        with self.assertRaises(OverlayConflictError):
            self.store.save(saved, expected_version=0)

    def test_retracted_overlay_cannot_transition_back(self) -> None:
        self.store.create("retired", session_id="retired")
        self.store.retract("retired", reason="bad teaching", actor="auditor")
        with self.assertRaises(Exception):
            self.store.transition("retired", "provisional_use", reason="revive")

    def test_corrupt_json_fails_closed(self) -> None:
        path = Path(self.tmp.name) / "broken.json"
        path.write_text('{"schema_version":', encoding="utf-8")
        with self.assertRaises(OverlayStoreError):
            self.store.load("broken")

    def test_atomic_save_leaves_valid_json(self) -> None:
        overlay = self.store.create("atomic", session_id="atomic")
        for index in range(5):
            overlay["metadata"]["index"] = index
            overlay = self.store.save(overlay, expected_version=overlay["version"])
            json.loads((Path(self.tmp.name) / "atomic.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
