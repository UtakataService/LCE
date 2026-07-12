import itertools
import unittest
from lce_validation.runtime.data_quality import DataQualityEvaluator, QualityResult, RawEvidence

def good(**changes):
    values=dict(evidence_id="e1", text="Water freezes at zero degrees Celsius.",
                source_uri="https://example.org/fact", license="CC-BY-4.0", language="en", consent=True)
    values.update(changes)
    return RawEvidence(**values)

class DataQualityTests(unittest.TestCase):
    def test_supported_languages_and_unicode(self):
        for lang,text in (("en","Water is transparent."),("ja","水は透明です。"),("vi","Nước trong suốt.")):
            with self.subTest(lang=lang): self.assertEqual(QualityResult.PASS, DataQualityEvaluator().evaluate(good(language=lang,text=text)).result)

    def test_hard_and_unknown_cases_never_become_candidates(self):
        cases=(good(text="x"), good(text="contact a@b.com"), good(license=None), good(language="und"),
               good(source_uri=""), good(consent=None), good(self_generated=True), good(text="mojibake Ã text"))
        for row in cases:
            report=DataQualityEvaluator().evaluate(row)
            self.assertFalse(report.candidate_eligible)
            self.assertNotEqual(QualityResult.PASS, report.result)

    def test_adversarial_cross_product_zero_false_accepts(self):
        total=false_accepts=0
        for license_,language,consent,source,text,self_generated in itertools.product(
            ("CC-BY-4.0",None,"PROPRIETARY"),("en","und",None),(True,False,None),
            ("https://example.org/x",""),("valid factual sentence","api_key=secret"),(False,True)):
            row=good(license=license_,language=language,consent=consent,source_uri=source,text=text,self_generated=self_generated)
            expected=license_=="CC-BY-4.0" and language=="en" and consent is True and bool(source) and text=="valid factual sentence" and not self_generated
            accepted=DataQualityEvaluator().evaluate(row).candidate_eligible
            false_accepts += int(accepted and not expected); total += 1
            self.assertEqual(expected, accepted)
        self.assertEqual(216,total); self.assertEqual(0,false_accepts)

    def test_duplicate_and_deletion_propagation(self):
        import hashlib
        digest="sha256:"+hashlib.sha256(b"Water freezes at zero degrees Celsius.").hexdigest()
        self.assertFalse(DataQualityEvaluator(known_hashes={digest}).evaluate(good()).candidate_eligible)
        self.assertFalse(DataQualityEvaluator(deleted_hashes={"sha256:p"}).evaluate(good(parent_hashes=("sha256:p",))).candidate_eligible)

if __name__ == "__main__": unittest.main()
