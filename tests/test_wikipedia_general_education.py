import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lce_validation.runtime.wikipedia_general_education import LICENSE,LICENSE_URL,bulk_ingest,make_record,public_metadata,query_shadow


PAGE={"title":"Water","extract":"Water is a transparent substance that is essential for known forms of life.","fullurl":"https://en.wikipedia.org/wiki/Water","revisions":[{"revid":123,"timestamp":"2026-01-01T00:00:00Z"}]}


class WikipediaGeneralEducationTests(unittest.TestCase):
    def test_record_keeps_attribution_and_revision(self):
        record=make_record(PAGE,"science")
        self.assertEqual(LICENSE,record.license)
        self.assertEqual(LICENSE_URL,record.license_url)
        self.assertEqual(123,record.revision_id)
        self.assertIn("Wikipedia contributors",record.attribution)
        self.assertTrue(record.revision_url.endswith("oldid=123"))
        self.assertEqual("SHADOW",record.status)

    def test_bulk_ingest_and_query_are_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); record=make_record(PAGE,"science")
            first=bulk_ingest([record],root); second=bulk_ingest([record],root)
            self.assertEqual(1,first["shadow"]); self.assertEqual(first["rows"],second["rows"])
            self.assertEqual("Water",query_shadow("water",root)[0]["title"])

    def test_missing_extract_is_rejected(self):
        with self.assertRaises(KeyError): make_record({"title":"Empty"},"science")

    def test_invalid_revision_category_or_active_status_is_quarantined(self):
        record=make_record(PAGE,"science")
        invalid=replace(record,revision_id=None,category="medical",status="ACTIVE")
        with tempfile.TemporaryDirectory() as td:
            manifest=bulk_ingest([invalid],Path(td))
            self.assertEqual(0,manifest["shadow"])
            self.assertEqual(1,manifest["quarantined"])

    def test_public_metadata_never_returns_excerpt(self):
        public=public_metadata([make_record(PAGE,"science").__dict__ if False else {"record_id":"x","excerpt":"hidden","title":"Water"}])[0]
        self.assertNotIn("excerpt",public)


if __name__=="__main__": unittest.main()
