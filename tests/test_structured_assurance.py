import pytest

from lce_validation.runtime.structured_assurance import (
    EvidenceClaim,
    StructuredAssuranceError,
    StructuredAssurancePolicy,
    assess_structured_value,
)


def _policy(**overrides):
    source = {
        "policy_id": "health-plan-v1",
        "required_values": {"request_kind": "implementation_plan"},
        "required_terms": {"summary": ["health"]},
        "forbidden_terms": ["haiku", "poem"],
        "certainty_path": "certainty",
        "known_values": ["known"],
        "evidence_refs_path": "evidence_refs",
        "required_evidence_claim_ids": ["evidence.health.read_only"],
    }
    source.update(overrides)
    return StructuredAssurancePolicy.from_dict(source)


def _value(**overrides):
    value = {
        "request_kind": "implementation_plan",
        "summary": "Add a health endpoint.",
        "certainty": "known",
        "evidence_refs": ["evidence.health.read_only"],
    }
    value.update(overrides)
    return value


def _catalog(disposition="supports"):
    return {"evidence.health.read_only": EvidenceClaim("evidence.health.read_only", disposition)}


def test_assurance_accepts_declared_intent_and_supporting_evidence():
    result = assess_structured_value(_value(), _policy(), _catalog())
    assert result["accepted"]
    assert result["violations"] == []


def test_assurance_rejects_lexical_intent_drift_even_when_shape_is_valid():
    result = assess_structured_value(_value(summary="A haiku about a budget."), _policy(), _catalog())
    assert not result["accepted"]
    assert "INTENT_REQUIRED_TERM_MISSING:summary" in result["violations"]
    assert "INTENT_FORBIDDEN_TERM_PRESENT:haiku" in result["violations"]


@pytest.mark.parametrize(
    ("disposition", "expected"),
    [("contradicts", "CERTAINTY_EVIDENCE_CONTRADICTED"), ("unknown", "CERTAINTY_EVIDENCE_UNSUPPORTED")],
)
def test_assurance_rejects_non_supporting_evidence(disposition, expected):
    result = assess_structured_value(_value(), _policy(), _catalog(disposition))
    assert not result["accepted"]
    assert expected in result["violations"]


def test_assurance_rejects_unknown_or_missing_required_evidence_refs():
    unknown = assess_structured_value(_value(evidence_refs=["evidence.unknown"]), _policy(), _catalog())
    assert "CERTAINTY_EVIDENCE_REF_UNKNOWN" in unknown["violations"]
    assert "CERTAINTY_EVIDENCE_REQUIRED_CLAIM_MISSING" in unknown["violations"]


def test_uncertain_value_does_not_require_evidence_binding():
    result = assess_structured_value(_value(certainty="uncertain", evidence_refs=[]), _policy(), {})
    assert result["accepted"]


def test_evidence_binding_requires_declared_paths():
    with pytest.raises(StructuredAssuranceError, match="ASSURANCE_EVIDENCE_PATH_REQUIRED"):
        StructuredAssurancePolicy.from_dict({"policy_id": "bad", "certainty_path": "certainty"})
