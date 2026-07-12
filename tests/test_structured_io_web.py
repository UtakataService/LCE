import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from lce_validation.web_ui import LceWebHandler


SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer"},
    },
    "required": ["name", "age"],
    "additionalProperties": False,
}


class StructuredIoWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LceWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, payload=None):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=3)
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {} if body is None else {"Content-Type": "application/json; charset=utf-8"}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        result = response.status, response.getheader("Content-Type"), raw
        connection.close()
        return result

    def test_html_exposes_structured_mode_and_utf8_japanese_defaults(self):
        status, content_type, raw = self.request("GET", "/")
        html = raw.decode("utf-8")
        self.assertEqual(200, status)
        self.assertEqual("text/html; charset=utf-8", content_type)
        self.assertIn('option value="structured"', html)
        self.assertIn('id="structuredData"', html)
        self.assertIn('id="structuredSchema"', html)
        self.assertIn("構造化入出力", html)
        self.assertIn("山田", html)

    def test_api_returns_canonical_structured_output_for_japanese_input(self):
        status, content_type, raw = self.request("POST", "/api/respond", {
            "mode": "structured",
            "text": "次のスキーマに従ってJSON形式で返してください",
            "data": {"name": "山田", "age": "30", "無視": "削除"},
            "schema": SCHEMA,
            "history": [],
        })
        body = json.loads(raw.decode("utf-8"))
        self.assertEqual(200, status)
        self.assertEqual("application/json; charset=utf-8", content_type)
        self.assertTrue(body["ok"])
        self.assertTrue(body["result"]["ok"])
        self.assertEqual("structured_output", body["result"]["route"])
        self.assertEqual({"age": 30, "name": "山田"}, body["result"]["structured_output"])
        self.assertEqual('{"age":30,"name":"山田"}', body["result"]["response"])

    def test_api_returns_bounded_rejection_without_transport_failure(self):
        status, content_type, raw = self.request("POST", "/api/respond", {
            "mode": "structured",
            "text": "JSON形式で返してください",
            "data": {"name": "山田"},
            "schema": SCHEMA,
            "history": [],
        })
        body = json.loads(raw.decode("utf-8"))
        self.assertEqual(200, status)
        self.assertEqual("application/json; charset=utf-8", content_type)
        self.assertTrue(body["ok"])
        self.assertFalse(body["result"]["ok"])
        self.assertEqual("structured_rejected", body["result"]["route"])
        self.assertIn("$.age:REQUIRED", body["result"]["errors"])

    def test_api_rejects_invalid_json_as_utf8_json_error(self):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=3)
        connection.request(
            "POST",
            "/api/respond",
            body=b'{"mode":"structured",',
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        response = connection.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type")
        connection.close()
        body = json.loads(raw.decode("utf-8"))
        self.assertEqual(400, response.status)
        self.assertEqual("application/json; charset=utf-8", content_type)
        self.assertFalse(body["ok"])
        self.assertTrue(body["error"])


if __name__ == "__main__":
    unittest.main()
