import tempfile
import unittest
from pathlib import Path

from lce_validation.runtime.coding_knowledge_corpus import build_units,bulk_ingest,query_shadow


class CodingKnowledgeCorpusTests(unittest.TestCase):
    def test_all_curated_units_pass_policy_and_tests(self):
        units=build_units()
        self.assertEqual(20,len(units))
        self.assertEqual(20,len({unit.task_type for unit in units}))
        self.assertTrue(all(unit.status=="SHADOW" for unit in units))
        self.assertTrue(all(unit.verification["ok"] for unit in units))

    def test_bulk_ingest_and_bilingual_query(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);manifest=bulk_ingest(build_units(),root)
            self.assertEqual(20,manifest["shadow"])
            self.assertEqual(60,manifest["test_cases"])
            self.assertEqual("binary_search",query_shadow("二分探索",root)[0]["task_type"])
            self.assertEqual("palindrome",query_shadow("palindrome",root)[0]["task_type"])

    def test_snapshot_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);bulk_ingest(build_units(),root);bulk_ingest(build_units(),root)
            self.assertEqual(20,len((root/"shadow_units.jsonl").read_text(encoding="utf-8").splitlines()))


if __name__=="__main__":unittest.main()
