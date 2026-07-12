import math
import unittest

from lce_validation.runtime.dialogue_state import (
    parse_utterance,
    respond_with_dialogue_state,
)


class DialogueStateAdversarialTests(unittest.TestCase):
    def test_identical_input_and_history_are_deterministic(self):
        history = [
            {"speaker": "user", "text": "Cube構造について", "topic": "cube"},
            {"speaker": "assistant", "text": "説明します"},
        ]
        first = respond_with_dialogue_state("それについて短く説明して", history)
        for _ in range(20):
            self.assertEqual(first, respond_with_dialogue_state("それについて短く説明して", history))

    def test_clarification_does_not_change_state(self):
        result = respond_with_dialogue_state("それについて", [])
        self.assertEqual("CLARIFY", result["decision"])
        self.assertEqual(result["state_before"], result["state_after"])
        self.assertEqual(result["state_hash_before"], result["state_hash_after"])

    def test_reference_candidate_requires_compatible_antecedents(self):
        result = respond_with_dialogue_state(
            "前者について詳しく教えて",
            [{"speaker": "user", "text": "Cube構造について"}],
        )
        self.assertEqual("CLARIFY", result["decision"])
        self.assertIn("REFERENCE_UNRESOLVED", result["reason_trace"])

    def test_ordinal_reference_requires_an_ordered_candidate_set(self):
        result = respond_with_dialogue_state(
            "二つ目を説明して",
            [{"speaker": "user", "text": "候補は一つだけです"}],
        )
        self.assertEqual("CLARIFY", result["decision"])

    def test_ambiguous_reference_does_not_emit_normal_answer(self):
        result = respond_with_dialogue_state(
            "それとその話について説明して",
            [
                {"speaker": "user", "text": "Cube構造"},
                {"speaker": "user", "text": "MySQL移行"},
            ],
        )
        self.assertEqual("CLARIFY", result["decision"])
        self.assertNotIn("answer", [chunk.get("kind") for chunk in result["output_chunks"]])

    def test_output_chunks_are_grounded_and_traceable(self):
        result = respond_with_dialogue_state("LCEについて詳しく教えて", [])
        for chunk in result["output_chunks"]:
            self.assertIn("chunk_id", chunk)
            self.assertIn("role", chunk)
            self.assertIn("text", chunk)
            self.assertTrue(chunk.get("support_refs"))
            self.assertIn(chunk.get("status"), {"GROUNDED", "BOUNDED"})
            self.assertTrue(chunk.get("reason_refs"))

    def test_reason_trace_has_structured_decisions(self):
        result = respond_with_dialogue_state("短く説明して、根拠も示して", [])
        trace = result["reason_trace"]
        self.assertIsInstance(trace, dict)
        self.assertEqual("reason_trace.v1", trace.get("schema_version"))
        self.assertTrue(trace.get("reasons"))
        for reason in trace["reasons"]:
            self.assertTrue({"reason_id", "stage", "decision", "code", "input_refs"} <= reason.keys())

    def test_utterance_frame_has_version_status_and_source_reference(self):
        frame = parse_utterance("それについて説明して")
        self.assertEqual("utterance_frame.v1", getattr(frame, "schema_version", None))
        self.assertIn(getattr(frame, "status", None), {"PASS", "AMBIGUOUS", "UNKNOWN"})
        self.assertIsNotNone(getattr(frame, "raw_input_ref", None))

    def test_intent_chain_is_not_only_an_untyped_string_list(self):
        result = respond_with_dialogue_state("短く説明して、根拠も示して", [])
        chain = result["intent_chain"]
        self.assertIsInstance(chain, dict)
        self.assertEqual("intent_chain.v1", chain.get("schema_version"))
        self.assertTrue(chain.get("intents"))
        self.assertIn("primary_intent_id", chain)

    def test_state_transition_is_explicit_and_revision_checked(self):
        result = respond_with_dialogue_state("LCEについて詳しく教えて", [])
        transition = result.get("state_transition")
        self.assertIsInstance(transition, dict)
        self.assertEqual("state_transition.v1", transition.get("schema_version"))
        self.assertEqual("PASS", transition.get("validation", {}).get("decision"))
        self.assertEqual(result["state_before"]["revision"], transition.get("expected_revision"))

    def test_confidences_are_finite_numbers_not_booleans(self):
        result = respond_with_dialogue_state("LCEについて詳しく教えて", [])
        frame = result["utterance_frame"]
        values = list(_confidence_values(frame))
        self.assertTrue(values, "UtteranceFrame must expose an explicit confidence")
        for value in values:
            self.assertIs(type(value), float)
            self.assertTrue(math.isfinite(value))
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_every_chunk_reason_reference_exists_in_trace(self):
        result = respond_with_dialogue_state("短く説明して、根拠も示して", [])
        reason_ids = {reason["reason_id"] for reason in result["reason_trace"]["reasons"]}
        for chunk in result["output_chunks"]:
            self.assertTrue(set(chunk["reason_refs"]) <= reason_ids)

    def test_output_chunk_text_composes_the_response(self):
        result = respond_with_dialogue_state(
            "説明して、そのあとJSONで返して",
            [{"speaker": "assistant", "schema": {"type": "object"}}],
        )
        emitted = [chunk["text"] for chunk in result["output_chunks"] if chunk["text"]]
        self.assertTrue(emitted)
        self.assertTrue(all(chunk["text"] for chunk in result["output_chunks"]))
        self.assertEqual("\n".join(emitted), result["response"])


def _confidence_values(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "confidence":
                yield item
            yield from _confidence_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _confidence_values(item)


if __name__ == "__main__":
    unittest.main()
