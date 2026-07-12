import unittest
from pathlib import Path

from lce_validation.schema_tools import load_json, validate_jsonl


class SchemaValidationTests(unittest.TestCase):
    def test_seed_fixtures_validate(self):
        schema = load_json(Path("lce_validation/schemas/fixture.schema.json"))
        errors = validate_jsonl("lce_validation/fixtures/seed_fixtures.jsonl", schema)
        self.assertEqual(errors, [])

    def test_seed_baselines_validate(self):
        schema = load_json(Path("lce_validation/schemas/baseline_run.schema.json"))
        errors = validate_jsonl("lce_validation/fixtures/seed_baselines.jsonl", schema)
        self.assertEqual(errors, [])
