import json
import unittest
from pathlib import Path


class FixtureContractTests(unittest.TestCase):
    def test_seed_fixtures_have_blocking_unknowns(self):
        rows = [json.loads(line) for line in Path("lce_validation/fixtures/seed_fixtures.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertGreaterEqual({row["fixture_family"] for row in rows}, {"DATA-F-A", "DATA-F-E", "DATA-F-F", "DATA-F-G"})
        self.assertTrue(all(row["contamination_ref"] == "contamination_unknown" for row in rows))
        self.assertTrue(all("ACCEPT_VERIFIED" in row["disallowed_outcomes"] for row in rows))
