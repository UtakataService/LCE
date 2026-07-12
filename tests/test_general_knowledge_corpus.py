import tempfile,unittest
from pathlib import Path
from lce_validation.runtime.general_knowledge_corpus import transform_bindings,bulk_ingest,query_shadow

SAMPLE=[{"country":{"value":"http://www.wikidata.org/entity/QX"},"countryLabel":{"value":"試験国"},"capital":{"value":"http://www.wikidata.org/entity/QY"},"capitalLabel":{"value":"試験首都"},"continent":{"value":"http://www.wikidata.org/entity/QZ"},"continentLabel":{"value":"試験大陸"},"currency":{"value":"http://www.wikidata.org/entity/QC"},"currencyLabel":{"value":"試験通貨"}}]
class GeneralKnowledgeCorpusTests(unittest.TestCase):
    def test_transform_creates_quality_gated_facts(self):
        facts=transform_bindings(SAMPLE);self.assertEqual(4,len(facts));self.assertTrue(all(x.status=="SHADOW" for x in facts));self.assertEqual({"instance_of","capital","continent","currency"},{x.predicate for x in facts})
    def test_bulk_ingest_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);facts=transform_bindings(SAMPLE);a=bulk_ingest(facts,root);b=bulk_ingest(facts,root)
            self.assertEqual(4,a["rows"]);self.assertEqual(4,b["rows"]);self.assertEqual(4,len((root/"shadow_facts.jsonl").read_text(encoding="utf-8").splitlines()))
            found=query_shadow("試験首都",root);self.assertEqual(1,len(found));self.assertEqual("capital",found[0]["predicate"])
    def test_ambiguous_subject_predicate_values_are_quarantined(self):
        second=dict(SAMPLE[0])
        second["capital"]={"value":"http://www.wikidata.org/entity/QY2"}
        second["capitalLabel"]={"value":"第二試験首都"}
        capitals=[x for x in transform_bindings([SAMPLE[0],second]) if x.predicate=="capital"]
        self.assertEqual(2,len(capitals))
        self.assertTrue(all(x.status=="QUARANTINED" for x in capitals))
if __name__=="__main__":unittest.main()
