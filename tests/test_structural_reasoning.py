import json
import tempfile
import unittest
from pathlib import Path

from lce_validation.empirical.engine import build_state_row, build_utterance_row, fixture_evidence_rows, run_empirical_slice, select_evidence
from lce_validation.empirical.reasoning import structural_decide


STRUCTURAL_FIXTURES = Path("lce_validation/fixtures/structural_reasoning_fixtures.jsonl")


def _load_fixture(fixture_id: str) -> dict:
    rows = [json.loads(line) for line in STRUCTURAL_FIXTURES.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["fixture_id"]: row for row in rows}[fixture_id]


class StructuralReasoningTests(unittest.TestCase):
    def test_decision_ignores_expected_outcome_when_evidence_supports_answer(self):
        fixture = _load_fixture("FX-STRUCT-EXPECTED-MISMATCH-001")
        evidence = fixture_evidence_rows(fixture)
        utterance = build_utterance_row(fixture)
        state = build_state_row(fixture, utterance, evidence)
        _, selected = select_evidence(fixture, evidence)
        decision = structural_decide(fixture, state, selected)
        self.assertEqual(decision["outcome"], "ACCEPT_CAVEATED")
        self.assertEqual(decision["structural_rule_id"], "direct_support")
        self.assertEqual(decision["status"], "blocked")

    def test_missing_support_metadata_is_unknown(self):
        fixture = _load_fixture("FX-STRUCT-MISSING-SUPPORT-001")
        evidence = fixture_evidence_rows(fixture)
        utterance = build_utterance_row(fixture)
        state = build_state_row(fixture, utterance, evidence)
        _, selected = select_evidence(fixture, evidence)
        decision = structural_decide(fixture, state, selected)
        self.assertEqual(decision["outcome"], "UNKNOWN_MODEL_GAP")
        self.assertEqual(decision["structural_rule_id"], "missing_support_metadata")

    def test_structural_fixture_run_writes_decision_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "structural01"
            summary = run_empirical_slice(STRUCTURAL_FIXTURES, out)
            self.assertTrue(summary["ok"])
            rows = [
                json.loads(line)
                for line in (out / "decision_rows.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(all("decision_inputs" in row for row in rows))
