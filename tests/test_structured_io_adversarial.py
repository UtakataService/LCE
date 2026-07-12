import math
import unittest

from lce_validation.runtime.structured_io import (
    MAX_ARRAY_ITEMS,
    MAX_DEPTH,
    run_structured_io,
)


def run(data, schema):
    return run_structured_io(instruction="Return JSON", data=data, schema=schema)


class StructuredIOAdversarialTests(unittest.TestCase):
    def test_bool_is_not_integer_or_number(self):
        for typ in ("integer", "number"):
            with self.subTest(typ=typ):
                self.assertFalse(run(True, {"type": typ})["ok"])

    def test_non_finite_numbers_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                self.assertFalse(run(value, {"type": "number"})["ok"])

    def test_schema_depth_limit_is_rejected(self):
        schema = {"type": "string"}
        data = "leaf"
        for _ in range(MAX_DEPTH + 1):
            schema = {"type": "array", "items": schema}
            data = [data]
        self.assertFalse(run(data, schema)["ok"])

    def test_oversized_array_is_rejected_not_truncated(self):
        schema = {
            "type": "array",
            "items": {"type": "integer"},
            "maxItems": MAX_ARRAY_ITEMS,
        }
        result = run(list(range(MAX_ARRAY_ITEMS + 1)), schema)
        self.assertFalse(result["ok"])

    def test_unsupported_keyword_is_rejected(self):
        self.assertFalse(run("x", {"type": "string", "pattern": "^x$"})["ok"])

    def test_object_requires_explicit_closed_world_contract(self):
        schema = {"type": "object", "properties": {}}
        self.assertFalse(run({}, schema)["ok"])

    def test_required_is_not_satisfied_by_default(self):
        schema = {
            "type": "object",
            "properties": {"id": {"type": "integer", "default": 7}},
            "required": ["id"],
            "additionalProperties": False,
        }
        self.assertFalse(run({}, schema)["ok"])

    def test_default_must_validate_against_its_subschema(self):
        schema = {
            "type": "object",
            "properties": {"id": {"type": "integer", "default": "wrong"}},
            "additionalProperties": False,
        }
        self.assertFalse(run({}, schema)["ok"])

    def test_enum_uses_type_sensitive_equality(self):
        self.assertFalse(run(True, {"type": "boolean", "enum": [1]})["ok"])

    def test_additional_input_keys_never_reach_output(self):
        schema = {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        }
        result = run({"id": 1, "secret": "drop-me"}, schema)
        self.assertTrue(result["ok"])
        self.assertEqual({"id": 1}, result["structured_output"])

    def test_output_is_deterministic_and_canonical(self):
        schema = {
            "type": "object",
            "properties": {
                "z": {"type": "integer"},
                "a": {"type": "string"},
            },
            "required": ["z", "a"],
            "additionalProperties": False,
        }
        responses = {
            run({"z": "2", "a": "x"}, schema)["response"] for _ in range(25)
        }
        self.assertEqual({'{"a":"x","z":2}'}, responses)


if __name__ == "__main__":
    unittest.main()
