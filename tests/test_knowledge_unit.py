import unittest
from datetime import datetime, timezone
from uuid import uuid4

from lce_validation.runtime.knowledge_unit import (
    Claim, ClaimObject, DecisionResult, EvidenceRelation, EvidenceStance,
    IntegrityViolation, InvalidTransition, KnowledgeRevision, LanguageState,
    Modality, ObjectKind, Scope, Status, Temporality, TransitionCommand,
    ValidationDecision, canonical_json, validate_transition,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def revision(status=Status.OBSERVED, *, scope=None, language=None, evidence=(), decisions=()):
    return KnowledgeRevision(
        unit_id=uuid4(), revision_id=uuid4(), revision_no=1,
        predecessor_revision_id=None, tenant_id="tenant-a", status=status,
        claim=Claim("surface:Xin cha\u0300o", "relation:means",
                    ClaimObject(ObjectKind.TEXT_LITERAL, "こんにちは"), modality=Modality.REPORTED),
        scope=scope or Scope(domain="greeting", language_variety="vi"),
        temporality=Temporality(recorded_at=NOW),
        language=language or LanguageState("vi", "vi", "und", "verified", "partial"),
        evidence=tuple(evidence), decisions=tuple(decisions),
    )


def command(row, target):
    return TransitionCommand(
        row.tenant_id, row.unit_id, row.revision_id, row.revision_no, target,
        {"id": "tester"}, "test", "ku-v1", f"key-{target.value}", NOW,
    )


class KnowledgeUnitDomainTests(unittest.TestCase):
    def test_unicode_is_nfc_in_canonical_json_without_language_guessing(self):
        row = revision(language=LanguageState("und", "und", "und", "hypothesized", "candidate"))
        encoded = canonical_json(row)
        self.assertIn("Xin chào", encoded)
        self.assertIn("こんにちは", encoded)
        self.assertIn('"expression_language":"und"', encoded)

    def test_invalid_valid_time_is_rejected(self):
        with self.assertRaises(IntegrityViolation):
            Temporality(valid_from=datetime(2026, 2, 1, tzinfo=timezone.utc),
                        valid_to=datetime(2026, 1, 1, tzinfo=timezone.utc), recorded_at=NOW)

    def test_state_machine_rejects_skip_and_reactivation(self):
        for source in (Status.OBSERVED, Status.NORMALIZED, Status.RETRACTED, Status.SUPERSEDED):
            with self.subTest(source=source), self.assertRaises(InvalidTransition):
                row = revision(source)
                validate_transition(row, command(row, Status.ACTIVE_L1))

    def test_active_gate_requires_scope_support_checks_and_decision(self):
        row = revision(Status.SHADOW, scope=Scope())
        with self.assertRaisesRegex(InvalidTransition, "scope|evidence|checks|decision"):
            validate_transition(row, command(row, Status.ACTIVE_L1))

    def test_unverified_language_cannot_be_promoted_even_with_other_gates(self):
        evidence = EvidenceRelation(uuid4(), EvidenceStance.SUPPORTS, "source-a", "tester", NOW)
        checks = tuple(ValidationDecision(name, DecisionResult.PASS, "blocking", "ku-v1", NOW)
                       for name in ("provenance", "license", "privacy", "contradiction", "regression"))
        decisions = checks + (ValidationDecision("promotion", DecisionResult.PASS, "blocking", "ku-v1", NOW,
                                                 promotion_decision=True),)
        row = revision(Status.SHADOW, language=LanguageState(identification_state="hypothesized"),
                       evidence=(evidence,), decisions=decisions)
        with self.assertRaisesRegex(InvalidTransition, "language"):
            validate_transition(row, command(row, Status.ACTIVE_L1))


if __name__ == "__main__":
    unittest.main()
