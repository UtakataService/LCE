"""Explicitly separate model content policy from LCE system integrity gates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class SafetyResponsibilityError(ValueError):
    pass


CONTENT_OPERATION = "content_generation"
INTEGRITY_OPERATIONS = frozenset({
    "schema_validation",
    "authorization",
    "state_commit",
    "external_execution",
    "sensitive_data_handling",
})


@dataclass(frozen=True, slots=True)
class SafetyResponsibilityPolicy:
    """Policy boundary for a model-backed LCE integration.

    LCE intentionally does not add a second content-safety refusal layer.
    It remains authoritative only for system-integrity operations that cannot
    safely be delegated to a text generator.
    """

    policy_id: str
    content_safety_owner: str = "model"
    local_content_blocking: bool = False

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SafetyResponsibilityPolicy":
        if not isinstance(value, Mapping):
            raise SafetyResponsibilityError("INVALID_SAFETY_RESPONSIBILITY_POLICY")
        policy = cls(
            policy_id=value.get("policy_id", ""),
            content_safety_owner=value.get("content_safety_owner", "model"),
            local_content_blocking=value.get("local_content_blocking", False),
        )
        _validate(policy)
        return policy


def resolve_safety_responsibility(
    operation: str,
    policy: SafetyResponsibilityPolicy | None = None,
) -> dict[str, Any]:
    """Return ownership without interpreting whether content is permissible."""
    effective = policy or SafetyResponsibilityPolicy(policy_id="default-model-content-safety")
    _validate(effective)
    if operation == CONTENT_OPERATION:
        return {
            "operation": operation,
            "owner": "model",
            "route": "DELEGATE_TO_MODEL",
            "lce_content_refusal": False,
            "claim_boundary": "LCE delegates content-safety judgement to the selected model and does not assess whether the content is permissible.",
        }
    if operation in INTEGRITY_OPERATIONS:
        return {
            "operation": operation,
            "owner": "lce",
            "route": "LCE_INTEGRITY_GATE",
            "lce_content_refusal": False,
            "claim_boundary": "This is a system-integrity gate, not a content-safety judgement.",
        }
    raise SafetyResponsibilityError("UNKNOWN_SAFETY_OPERATION")


def _validate(policy: SafetyResponsibilityPolicy) -> None:
    if not isinstance(policy, SafetyResponsibilityPolicy) or not isinstance(policy.policy_id, str) or not policy.policy_id:
        raise SafetyResponsibilityError("INVALID_SAFETY_RESPONSIBILITY_POLICY")
    if policy.content_safety_owner != "model" or policy.local_content_blocking is not False:
        raise SafetyResponsibilityError("CONTENT_SAFETY_MUST_BE_MODEL_OWNED")
