import json
import unittest
import tempfile
from pathlib import Path

from lce_validation.cli import run_smoke


class EventReplaySmokeTests(unittest.TestCase):
    def test_event_replay_smoke(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "smoke01"
            self.assertEqual(run_smoke(str(out)), 0)
            manifest = json.loads((out / "replay_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["replay_manifest_id"], "replay-smoke01")
            self.assertTrue(manifest["event_hashes"])
            self.assertTrue((out / "pi_service_probe_dryrun.json").exists())
