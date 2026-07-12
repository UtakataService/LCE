import pytest

from lce_validation.runtime.safety_responsibility import (
    SafetyResponsibilityError,
    SafetyResponsibilityPolicy,
    resolve_safety_responsibility,
)


def test_content_safety_is_delegated_to_the_model_without_lce_refusal():
    result = resolve_safety_responsibility("content_generation")
    assert result["owner"] == "model"
    assert result["route"] == "DELEGATE_TO_MODEL"
    assert result["lce_content_refusal"] is False


def test_integrity_operations_remain_lce_owned_without_becoming_content_judgements():
    result = resolve_safety_responsibility("state_commit")
    assert result["owner"] == "lce"
    assert result["route"] == "LCE_INTEGRITY_GATE"
    assert result["lce_content_refusal"] is False


def test_policy_rejects_double_content_blocking_configuration():
    with pytest.raises(SafetyResponsibilityError, match="CONTENT_SAFETY_MUST_BE_MODEL_OWNED"):
        SafetyResponsibilityPolicy.from_dict({
            "policy_id": "double-block",
            "content_safety_owner": "lce",
            "local_content_blocking": True,
        })


def test_unknown_operation_is_not_silently_classified_as_a_safety_gate():
    with pytest.raises(SafetyResponsibilityError, match="UNKNOWN_SAFETY_OPERATION"):
        resolve_safety_responsibility("unknown_operation")
