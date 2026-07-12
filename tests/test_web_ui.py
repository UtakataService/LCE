import tempfile
import unittest
from unittest.mock import patch

import lce_validation.web_ui as web_ui
from lce_validation.runtime.language_overlay_store import LanguageOverlayStore
from lce_validation.web_ui import _UNKNOWN_LANGUAGE_SESSIONS, dispatch_response


class WebUiTests(unittest.TestCase):
    def tearDown(self):
        _UNKNOWN_LANGUAGE_SESSIONS.clear()

    def test_dispatch_topic_response(self):
        result = dispatch_response({
            "mode": "topic",
            "text": "Continue this chunk seed composition approach.",
            "history": [{"speaker": "user", "text": "Use chunk-sized seeds."}],
        })
        self.assertTrue(result["ok"])
        self.assertIn(result["route"], {"topic_continue", "history_chunk_plan", "chunk_plan"})

    def test_dispatch_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            dispatch_response({"mode": "missing", "text": "hello", "history": []})

    def test_dispatch_coding_response(self):
        result = dispatch_response({
            "mode": "coding",
            "text": "Write a Python function solve(numbers) that returns the sum of a list of numbers.",
            "history": [],
        })
        self.assertTrue(result["ok"])
        self.assertEqual(result["route"], "coding_pass")
        self.assertTrue(result["verification"]["ok"])

    @patch("lce_validation.web_ui.run_unknown_language_session")
    def test_dispatch_unknown_language_contract(self, runtime):
        runtime.return_value = {
            "ok": True,
            "session_id": "vi-first-contact",
            "acquisition_state": "provisional_use",
            "hypotheses": [{"form": "xin chao", "meaning": "hello", "confidence": 0.72}],
            "confidence": {"meaning": 0.72, "grammar": 0.18},
            "broken_response": "Xin chao.",
        }

        result = dispatch_response({
            "mode": "unknown_language",
            "session_id": "vi-first-contact",
            "text": "Xin chao",
            "observation": "Xin chao",
            "teaching": "This is a greeting.",
            "history": [],
        })

        self.assertEqual(result["session_id"], "vi-first-contact")
        self.assertEqual(result["broken_response"], "Xin chao.")
        self.assertEqual(result["hypotheses"][0]["meaning"], "hello")
        runtime.assert_called_once_with(
            session_id="vi-first-contact",
            observation="Xin chao",
            teaching="This is a greeting.",
            history=[],
        )

    def test_unknown_language_requires_session_id(self):
        with self.assertRaisesRegex(ValueError, "session_id"):
            dispatch_response({"mode": "unknown_language", "text": "Xin chao", "history": []})

    def test_unknown_language_rejects_invalid_teaching_type(self):
        with self.assertRaisesRegex(ValueError, "teaching"):
            dispatch_response({
                "mode": "unknown_language",
                "session_id": "vi-1",
                "text": "Xin chao",
                "teaching": 42,
                "history": [],
            })

    def test_unknown_language_runtime_keeps_sessions_isolated(self):
        taught = dispatch_response({
            "mode": "unknown_language",
            "session_id": "vi-a",
            "observation": "Xin chao",
            "teaching": {
                "form": "xin chao",
                "meaning": "hello",
                "confirmed": True,
                "requested_meanings": ["hello"],
            },
            "history": [],
        })
        untouched = dispatch_response({
            "mode": "unknown_language",
            "session_id": "vi-b",
            "observation": "Xin chao",
            "history": [],
        })

        self.assertEqual(taught["broken_response"], "xin chao")
        self.assertTrue(any(item.get("meaning") == "hello" for item in taught["hypotheses"]))
        self.assertFalse(any(item.get("meaning") == "hello" for item in untouched["hypotheses"]))
        self.assertFalse(taught["formal_knowledge"])

    def test_plain_teaching_remains_provisional(self):
        result = dispatch_response({
            "mode": "unknown_language",
            "session_id": "vi-provisional",
            "observation": "Xin chao",
            "teaching": "xin chao = hello",
            "history": [],
        })

        self.assertIn("Does", result["broken_response"])
        lexical = [item for item in result["hypotheses"] if item.get("kind") == "lexical"]
        self.assertEqual(lexical[0]["confirmed"], False)

    def test_unknown_language_overlay_restores_after_store_reopen(self):
        with tempfile.TemporaryDirectory() as root:
            original = web_ui._UNKNOWN_LANGUAGE_STORE
            try:
                web_ui._UNKNOWN_LANGUAGE_STORE = LanguageOverlayStore(root)
                taught = dispatch_response({
                    "mode": "unknown_language",
                    "session_id": "restart-proof",
                    "observation": "mivako",
                    "teaching": {"form": "mivako", "meaning": "hello", "confirmed": True},
                    "history": [],
                })
                web_ui._UNKNOWN_LANGUAGE_STORE = LanguageOverlayStore(root)
                restored = dispatch_response({
                    "mode": "unknown_language",
                    "session_id": "restart-proof",
                    "observation": "mivako",
                    "history": [],
                })
                persisted = web_ui._UNKNOWN_LANGUAGE_STORE.load("restart-proof")
            finally:
                web_ui._UNKNOWN_LANGUAGE_STORE = original
        self.assertGreater(restored["overlay_version"], taught["overlay_version"])
        self.assertTrue(any(item.get("meaning") == "hello" for item in restored["hypotheses"]))
        self.assertEqual(persisted["evidence"][0]["kind"], "grounded_teaching")
