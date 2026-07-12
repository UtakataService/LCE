import itertools
import json
import math
import unittest

from lce_validation.runtime.structured_io import *
from lce_validation.web_ui import dispatch_response


SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}, "age": {"type": "integer"}, "role": {"type": "string", "enum": ["user", "admin"]}}, "required": ["name", "age"], "additionalProperties": False}


class StructuredIOTests(unittest.TestCase):
    def test_recognition_three_way_real_japanese(self):
        self.assertEqual(Intent.YES, recognize_structured_request("JSON形式で返して"))
        self.assertEqual(Intent.NO, recognize_structured_request("JSONとは何ですか"))
        self.assertEqual(Intent.NO, recognize_structured_request("JSONについて説明して"))
        self.assertEqual(Intent.AMBIGUOUS, recognize_structured_request("項目にまとめて出力して"))

    def test_valid_generation_and_canonical_json(self):
        result = run_structured_io(instruction="次のスキーマに従ってJSONで", data={"name": "山田", "age": "30", "ignored": "x"}, schema=SCHEMA)
        self.assertTrue(result["ok"])
        self.assertEqual({"age": 30, "name": "山田"}, json.loads(result["response"]))

    def test_missing_required_and_enum_fail_closed(self):
        self.assertFalse(run_structured_io(instruction="JSONで", data={"name": "A"}, schema=SCHEMA)["ok"])
        self.assertFalse(run_structured_io(instruction="JSONで", data={"name": "A", "age": 2, "role": "root"}, schema=SCHEMA)["ok"])

    def test_closed_schema_and_unknown_keywords_required(self):
        bad = [
            {"type": "object", "properties": {}, "additionalProperties": True},
            {"type": "object", "properties": {}, "additionalProperties": False, "oneOf": []},
            {"type": "object", "properties": {}},
            {"type": "string", "default": "invented"},
            {"type": "string", "items": {"type": "string"}},
        ]
        for schema in bad:
            with self.subTest(schema=schema):
                self.assertFalse(run_structured_io(instruction="JSONで", data={}, schema=schema)["ok"])

    def test_enum_type_integrity(self):
        for enum in ([True], [1, True], [1, 1.0]):
            schema = {"type": "integer", "enum": enum}
            self.assertFalse(run_structured_io(instruction="JSONで", data=1, schema=schema)["ok"])

    def test_non_finite_numbers_rejected(self):
        schema = {"type": "number"}
        for value in (math.nan, math.inf, -math.inf):
            self.assertFalse(run_structured_io(instruction="JSONで", data=value, schema=schema)["ok"])
        self.assertFalse(run_structured_io(instruction="JSONで", data=1, schema='{"type":"number","enum":[NaN]}')["ok"])

    def test_array_limits_fail_instead_of_truncating(self):
        schema = {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 2}
        self.assertTrue(run_structured_io(instruction="JSONで", data=[1, 2], schema=schema)["ok"])
        self.assertFalse(run_structured_io(instruction="JSONで", data=[1, 2, 3], schema=schema)["ok"])
        for invalid in (-1, True, 101):
            bad = {"type": "array", "items": {"type": "integer"}, "maxItems": invalid}
            self.assertFalse(run_structured_io(instruction="JSONで", data=[], schema=bad)["ok"])

    def test_adversarial_types_zero_false_accept(self):
        values = (None, True, 1, 1.5, "1", [], {})
        false_accept = 0
        for name, age in itertools.product(values, repeat=2):
            result = run_structured_io(instruction="JSONで", data={"name": name, "age": age}, schema=SCHEMA)
            expected = isinstance(name, str) and ((isinstance(age, int) and not isinstance(age, bool)) or age == "1")
            false_accept += int(result["ok"] and not expected)
        self.assertEqual(0, false_accept)

    def test_embedded_schema(self):
        result = run_structured_io(instruction="JSON形式で返して\n```json\n" + json.dumps(SCHEMA) + "\n```", data={"name": "A", "age": 4})
        self.assertTrue(result["ok"])

    def test_web_dispatch(self):
        result = dispatch_response({"mode": "structured", "text": "このスキーマに従ってJSON形式で返して", "data": {"name": "山田", "age": "30"}, "schema": SCHEMA, "history": []})
        self.assertTrue(result["ok"])
        self.assertEqual("structured_output", result["route"])

    def test_explicit_json_refusal_overrides_attached_schema(self):
        result = run_structured_io(instruction="JSONでは返さないで", data={"name":"A","age":1}, schema=SCHEMA)
        self.assertFalse(result["ok"])
        self.assertEqual("normal_dialogue", result["route"])
