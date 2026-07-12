from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lce_validation.runtime.language_overlay_store import LanguageOverlayStore
from lce_validation.runtime.mysql_overlay_repository import MySQLLanguageOverlayRepository
from lce_validation.runtime.overlay_repository import create_overlay_repository


ROOT = Path(__file__).resolve().parents[1]


class OverlayRepositoryContractTests(unittest.TestCase):
    def test_json_backend_is_default_and_round_trips_unicode(self) -> None:
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"LCE_OVERLAY_BACKEND": "json", "LCE_LANGUAGE_OVERLAY_ROOT": root}, clear=False):
            repository = create_overlay_repository()
            self.assertIsInstance(repository, LanguageOverlayStore)
            overlay = repository.create("vi", session_id="vi", source_language="vi", metadata={"surface": "Xin chào"})
            self.assertEqual(repository.load("vi")["metadata"]["surface"], "Xin chào")
            self.assertEqual(overlay["version"], 0)

    def test_unknown_backend_fails_closed(self) -> None:
        with patch.dict(os.environ, {"LCE_OVERLAY_BACKEND": "surprise"}, clear=False):
            with self.assertRaisesRegex(ValueError, "unsupported"):
                create_overlay_repository()

    def test_mysql_ddl_fixes_storage_and_concurrency_contract(self) -> None:
        ddl = (ROOT / "lce_validation" / "schemas" / "mysql_v1.sql").read_text(encoding="utf-8")
        for fragment in ("utf8mb4", "ENGINE=InnoDB", "payload_json JSON", "version BIGINT", "knowledge_units", "knowledge_evidence", "graph_edges"):
            self.assertIn(fragment, ddl)

    def test_mysql_payload_preserves_unicode_without_ascii_escaping(self) -> None:
        payload = MySQLLanguageOverlayRepository._payload({"surface": "Xin chào"})
        self.assertIn("Xin chào", payload)
        self.assertNotIn("\\u00e0", payload)


if __name__ == "__main__":
    unittest.main()
