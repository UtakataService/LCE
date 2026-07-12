import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from lce_validation.runtime.web_knowledge_intake import IntakeError,extract_text,intake_url,list_intakes,_public_url

class WebKnowledgeIntakeTests(unittest.TestCase):
    def test_html_extracts_visible_text(self):
        text=extract_text(b"<html><style>x</style><h1>Title</h1><p>Useful public knowledge text.</p><script>x</script></html>","text/html")
        self.assertIn("Title",text); self.assertNotIn("<h1>",text); self.assertNotIn("script",text)
    def test_private_and_nonstandard_urls_are_blocked(self):
        for url in ("http://127.0.0.1/x","http://localhost/x","file:///etc/passwd","https://example.com:8443/x"):
            with self.subTest(url=url),self.assertRaises(IntakeError): _public_url(url)
    @patch("lce_validation.runtime.web_knowledge_intake._public_url")
    def test_unknown_rights_quarantines_and_deduplicates(self,_):
        with tempfile.TemporaryDirectory() as td:
            args=dict(url="https://example.org/a",language="ja",root=Path(td),body="一般知識として保存する十分な長さの日本語本文です。追加の説明も含みます。".encode(),content_type="text/plain")
            first=intake_url(**args); second=intake_url(**args)
            self.assertEqual("QUARANTINED",first["record"]["status"]); self.assertFalse(first["duplicate"]); self.assertTrue(second["duplicate"])
            self.assertEqual(1,len(list_intakes(Path(td))))
    @patch("lce_validation.runtime.web_knowledge_intake._public_url")
    def test_confirmed_allowed_content_becomes_shadow_only(self,_):
        with tempfile.TemporaryDirectory() as td:
            result=intake_url("https://example.org/a",language="en",license="CC-BY-4.0",rights_confirmed=True,root=Path(td),
                              body=b"This is sufficiently long public knowledge content for a quality-gated intake record.",content_type="text/plain")
            self.assertEqual("SHADOW_CANDIDATE",result["record"]["status"])
    def test_json_is_canonicalized(self):
        self.assertEqual('{"a": 1, "b": 2}',extract_text(b'{"b":2,"a":1}',"application/json"))

if __name__=="__main__":unittest.main()
