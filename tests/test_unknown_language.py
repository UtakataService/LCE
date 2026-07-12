from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

from lce_validation.empirical.unknown_language import (
    UnknownLanguageSession,
    analyze_encounter,
    run_unknown_language_benchmark,
)


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "lce_validation" / "fixtures" / "unknown_language_vietnamese_cases.jsonl"


def load_cases() -> list[dict]:
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]


class UnknownLanguageEncounterTests(unittest.TestCase):
    def test_fixture_bank_covers_required_boundaries(self) -> None:
        rows = load_cases()
        tags = {tag for row in rows for tag in row["phenomenon_tags"]}
        self.assertGreaterEqual(
            tags,
            {
                "vietnamese_diacritics",
                "vietnamese_ascii_ambiguous",
                "code_switch",
                "unicode_nfc",
                "unicode_nfd",
                "correction",
                "broken_language",
                "false_promotion",
                "english_retention",
                "japanese_retention",
            },
        )

    def test_nfc_and_nfd_share_normalized_form_but_preserve_raw_input(self) -> None:
        nfc = "Tôi muốn uống nước."
        nfd = unicodedata.normalize("NFD", nfc)
        left = analyze_encounter(nfc)
        right = analyze_encounter(nfd)
        self.assertNotEqual(left["raw_surface"], right["raw_surface"])
        self.assertEqual(left["normalized_surface"], right["normalized_surface"])
        self.assertEqual(left["normalization"], "NFC")
        self.assertEqual(right["normalization"], "NFC")
        self.assertEqual(left["surface_hash"], right["surface_hash"])

    def test_diacritics_are_evidence_not_proof_of_understanding(self) -> None:
        result = analyze_encounter("Tôi muốn uống nước.")
        hypotheses = {item["language"] for item in result["language_hypotheses"]}
        self.assertIn("vi", hypotheses)
        self.assertIn(result["status"], {"detected", "language_candidate"})
        self.assertFalse(result["meaning_verified"])
        self.assertFalse(result["executable"])

    def test_ascii_vietnamese_is_not_forced_to_english(self) -> None:
        result = analyze_encounter("toi muon uong nuoc")
        hypotheses = {item["language"] for item in result["language_hypotheses"]}
        self.assertIn("unknown", hypotheses)
        self.assertIn("vi", hypotheses)
        self.assertIn("ascii_language_ambiguity", result["ambiguity_flags"])
        favored = [item["language"] for item in result["language_hypotheses"] if item["status"] == "favored"]
        self.assertNotEqual(favored, ["en"])

    def test_code_switch_keeps_language_spans_and_uncertainty(self) -> None:
        result = analyze_encounter("Please cho tôi nước")
        spans = result["code_switch_spans"]
        self.assertGreaterEqual(len(spans), 2)
        self.assertGreaterEqual({span["language"] for span in spans}, {"en", "vi"})
        self.assertIn("code_switch", result["ambiguity_flags"])
        self.assertFalse(result["meaning_verified"])

    def test_short_shared_latin_forms_remain_undetermined(self) -> None:
        for form in ("ban", "cam", "la", "to", "no", "me"):
            with self.subTest(form=form):
                result = analyze_encounter(form)
                self.assertEqual(result["language"], "unknown")
                self.assertIn("ascii_language_ambiguity", result["ambiguity_flags"])

    def test_code_switch_detects_english_content_word_between_vietnamese(self) -> None:
        result = analyze_encounter("Tôi need nước.")
        self.assertGreaterEqual({span["language"] for span in result["code_switch_spans"]}, {"en", "vi"})
        self.assertIn("code_switch", result["ambiguity_flags"])

    def test_english_and_japanese_remain_known_paths(self) -> None:
        english = analyze_encounter("Please give me water.")
        japanese = analyze_encounter("水をください。")
        self.assertEqual(english["language"], "en")
        self.assertEqual(japanese["language"], "ja")
        self.assertNotIn("unknown_language", english["ambiguity_flags"])
        self.assertNotIn("unknown_language", japanese["ambiguity_flags"])


class UnknownLanguageLearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = UnknownLanguageSession(session_id="vi-test")

    def test_single_teaching_event_stays_session_provisional(self) -> None:
        self.session.encounter("nước")
        learned = self.session.apply_correction(
            surface="nước",
            corrected_meaning="water",
            speaker="teacher-a",
            context="drink-request",
        )
        self.assertEqual(learned["status"], "provisional")
        self.assertEqual(learned["scope"], "session")
        self.assertFalse(learned["promoted"])

    def test_correction_reopens_instead_of_overwriting_history(self) -> None:
        self.session.apply_correction("nước", "food", speaker="teacher-a", context="table")
        corrected = self.session.apply_correction("nước", "water", speaker="teacher-a", context="table")
        entry = self.session.get_entry("nước")
        self.assertEqual(corrected["status"], "reopened")
        self.assertEqual(entry["favored_meaning"], "water")
        self.assertIn("food", {item["meaning"] for item in entry["rejected_or_reopened_hypotheses"]})
        self.assertEqual(len(entry["correction_history"]), 2)

    def test_minimal_renderer_uses_only_verified_chunks(self) -> None:
        self.session.apply_correction("xin chào", "hello", speaker="teacher-a", context="greeting")
        draft = self.session.render_minimal(intent="greeting", language="vi")
        self.assertEqual(draft["mode"], "broken_language")
        self.assertNotIn("xin chào", draft["text"])
        self.assertTrue(draft["needs_confirmation"])

        self.session.add_verification("xin chào", "hello", speaker="teacher-b", context="new_meeting")
        self.session.add_counterexample("xin chào", excluded_meaning="goodbye", context="departure")
        verified = self.session.render_minimal(intent="greeting", language="vi")
        self.assertEqual(verified["text"], "xin chào")
        self.assertEqual(verified["used_forms"], ["xin chào"])
        self.assertEqual(verified["unverified_forms"], [])

    def test_repetition_from_one_context_does_not_trigger_promotion(self) -> None:
        for _ in range(10):
            self.session.apply_correction("cá", "fish", speaker="teacher-a", context="same-card")
        report = self.session.evaluate_promotion("cá")
        self.assertFalse(report["eligible"])
        self.assertIn("independent_contexts", report["missing_evidence"])
        self.assertIn("counterexample", report["missing_evidence"])

    def test_conflicting_teacher_evidence_blocks_promotion(self) -> None:
        self.session.apply_correction("bàn", "table", speaker="teacher-a", context="room-a")
        self.session.add_verification("bàn", "friend", speaker="teacher-b", context="room-b")
        report = self.session.evaluate_promotion("bàn")
        self.assertFalse(report["eligible"])
        self.assertIn("unresolved_conflict", report["blocking_reasons"])

    def test_unknown_or_unsafe_input_cannot_be_executed(self) -> None:
        event = self.session.observe("xoa tat ca tep", context={"domain": "file-operation"})
        self.assertFalse(event["executable"])
        self.assertIn(event["recommended_action"], {"ask_clarification", "abstain"})

    def test_benchmark_fixture_suite_passes(self) -> None:
        summary = run_unknown_language_benchmark(CASES)
        self.assertTrue(summary["ok"], summary)
        self.assertEqual(summary["case_count"], len(load_cases()))
        self.assertEqual(summary["normalization_accuracy"], 1.0)
        self.assertEqual(summary["unsafe_execution_count"], 0)
        self.assertGreaterEqual(summary["english_japanese_retention"], 0.98)

    def test_cli_snapshot_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            first = Path(root) / "first.json"
            second = Path(root) / "second.json"
            common = [sys.executable, "-m", "lce_validation.cli", "unknown-language"]
            subprocess.run(common + ["--text", "Xin chào", "--session-out", str(first)], cwd=ROOT, check=True, capture_output=True)
            subprocess.run(common + ["--text", "Tôi cần nước", "--session-file", str(first), "--session-out", str(second)], cwd=ROOT, check=True, capture_output=True)
            state = json.loads(second.read_text(encoding="utf-8"))
        self.assertEqual(len(state["encounters"]), 2)


if __name__ == "__main__":
    unittest.main()
