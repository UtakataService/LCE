"""Backend-neutral, fail-closed Knowledge Unit promotion policy core."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import hmac
from typing import Any, Mapping, Sequence

from .knowledge_unit import canonical_hash, canonical_json


POLICY_VERSION = "promotion-gate/v1"
REQUIRED_HARD_CHECKS = (
    "provenance_complete",
    "evidence_integrity",
    "source_independence",
    "semantic_stability",
    "contradiction_review",
    "privacy_review",
    "license_review",
    "language_verification",
    "regression_review",
    "risk_classification",
    "promotion_decision",
)


class PromotionGateError(ValueError):
    pass


class CheckResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class RiskClass(str, Enum):
    LOW = "low-risk"
    NORMAL = "normal"
    HIGH = "high-risk"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


class ActorType(str, Enum):
    HUMAN = "human"
    SERVICE = "service"


@dataclass(frozen=True, slots=True)
class Actor:
    actor_id: str
    actor_type: ActorType
    tenant_id: str
    roles: frozenset[str]

    def __post_init__(self) -> None:
        if not self.actor_id.strip() or not self.tenant_id.strip() or not self.roles:
            raise PromotionGateError("actor identity, tenant, and roles are required")


@dataclass(frozen=True, slots=True)
class HardCheck:
    name: str
    result: CheckResult
    check_version: str
    snapshot_hash: str
    checked_by: str
    checked_at: datetime
    expires_at: datetime | None = None
    reason_codes: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.name not in REQUIRED_HARD_CHECKS:
            raise PromotionGateError(f"unknown hard check: {self.name}")
        if not self.check_version.strip() or not self.snapshot_hash.strip() or not self.checked_by.strip():
            raise PromotionGateError("check version, snapshot, and checker are required")
        if self.checked_at.tzinfo is None or (self.expires_at and self.expires_at.tzinfo is None):
            raise PromotionGateError("check timestamps must be timezone-aware")
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True, slots=True)
class HumanApproval:
    approval_id: str
    tenant_id: str
    unit_id: str
    revision_id: str
    snapshot_hash: str
    policy_version: str
    approver: Actor
    approved: bool
    approved_at: datetime
    expires_at: datetime | None = None
    signature: str = ""

    def __post_init__(self) -> None:
        if self.approver.actor_type is not ActorType.HUMAN:
            raise PromotionGateError("human approval requires a human actor")
        if "human_approver" not in self.approver.roles:
            raise PromotionGateError("approver lacks human_approver role")
        if self.approved_at.tzinfo is None or (self.expires_at and self.expires_at.tzinfo is None):
            raise PromotionGateError("approval timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class PromotionRequest:
    tenant_id: str
    unit_id: str
    revision_id: str
    expected_revision_no: int
    status: str
    snapshot_hash: str
    current_snapshot_hash: str
    policy_version: str
    risk_class: RiskClass
    submitter: Actor
    reviewer: Actor
    executor: Actor
    checks: tuple[HardCheck, ...]
    requested_at: datetime
    human_approval: HumanApproval | None = None

    def __post_init__(self) -> None:
        if self.expected_revision_no < 1 or self.requested_at.tzinfo is None:
            raise PromotionGateError("positive revision and aware request time are required")
        if not all(value.strip() for value in (
            self.tenant_id, self.unit_id, self.revision_id, self.snapshot_hash,
            self.current_snapshot_hash, self.policy_version,
        )):
            raise PromotionGateError("promotion target metadata is incomplete")


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    eligible: bool
    result: CheckResult
    tenant_id: str
    unit_id: str
    revision_id: str
    snapshot_hash: str
    policy_version: str
    risk_class: RiskClass
    decided_at: datetime
    executor_id: str
    reason_codes: tuple[str, ...]
    check_results: tuple[tuple[str, str], ...]
    decision_hash: str
    signature_algorithm: str
    key_id: str
    signature: str


def compute_snapshot_hash(snapshot: Any) -> str:
    return "sha256:" + canonical_hash(snapshot)


def _unsigned_payload(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key not in {"decision_hash", "signature"}}


def verify_signed_decision(decision: PromotionDecision, secret: bytes) -> bool:
    payload = _unsigned_payload(asdict(decision))
    digest = "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    expected = hmac.new(secret, digest.encode("ascii"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(decision.decision_hash, digest) and hmac.compare_digest(
        decision.signature, expected
    )


class PromotionGate:
    def __init__(self, signing_key: bytes, *, key_id: str = "promotion-v1") -> None:
        if len(signing_key) < 32:
            raise PromotionGateError("signing key must contain at least 32 bytes")
        if not key_id.strip():
            raise PromotionGateError("key_id is required")
        self._key = bytes(signing_key)
        self._key_id = key_id

    def evaluate(self, request: PromotionRequest, *, now: datetime | None = None) -> PromotionDecision:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise PromotionGateError("evaluation time must be timezone-aware")
        reasons: list[str] = []

        if request.status != "SHADOW":
            reasons.append("STATUS_NOT_SHADOW")
        if request.policy_version != POLICY_VERSION:
            reasons.append("POLICY_VERSION_MISMATCH")
        if request.snapshot_hash != request.current_snapshot_hash:
            reasons.append("STALE_SNAPSHOT")
        actors = (request.submitter, request.reviewer, request.executor)
        if any(actor.tenant_id != request.tenant_id for actor in actors):
            reasons.append("ACTOR_TENANT_MISMATCH")
        if "reviewer" not in request.reviewer.roles:
            reasons.append("REVIEWER_ROLE_MISSING")
        if "promotion_executor" not in request.executor.roles:
            reasons.append("EXECUTOR_ROLE_MISSING")
        if request.submitter.actor_id == request.reviewer.actor_id:
            reasons.append("SUBMITTER_SELF_REVIEW")
        if request.executor.actor_id in {request.submitter.actor_id, request.reviewer.actor_id}:
            reasons.append("EXECUTOR_NOT_SEPARATED")
        if request.risk_class is RiskClass.UNKNOWN:
            reasons.append("RISK_CLASS_UNKNOWN")

        grouped: dict[str, list[HardCheck]] = {}
        for check in request.checks:
            grouped.setdefault(check.name, []).append(check)
        for name in REQUIRED_HARD_CHECKS:
            candidates = grouped.get(name, [])
            if len(candidates) != 1:
                reasons.append("CHECK_MISSING" if not candidates else "CHECK_DUPLICATE")
                continue
            check = candidates[0]
            if check.snapshot_hash != request.snapshot_hash:
                reasons.append(f"CHECK_SNAPSHOT_MISMATCH:{name}")
            if check.expires_at is not None and check.expires_at <= now:
                reasons.append(f"CHECK_EXPIRED:{name}")
            if check.result is CheckResult.FAIL:
                reasons.append(f"CHECK_FAIL:{name}")
            elif check.result is CheckResult.UNKNOWN:
                reasons.append(f"CHECK_UNKNOWN:{name}")

        approval_required = request.risk_class in {RiskClass.HIGH, RiskClass.VOLATILE}
        approval = request.human_approval
        if approval_required and approval is None:
            reasons.append("HUMAN_APPROVAL_REQUIRED")
        if approval is not None:
            self._validate_approval(request, approval, now, reasons)

        eligible = not reasons
        result = CheckResult.PASS if eligible else (
            CheckResult.UNKNOWN if any("UNKNOWN" in item or "MISSING" in item for item in reasons)
            else CheckResult.FAIL
        )
        check_results = tuple(sorted((check.name, check.result.value) for check in request.checks))
        base = {
            "eligible": eligible, "result": result, "tenant_id": request.tenant_id,
            "unit_id": request.unit_id, "revision_id": request.revision_id,
            "snapshot_hash": request.snapshot_hash, "policy_version": request.policy_version,
            "risk_class": request.risk_class, "decided_at": now,
            "executor_id": request.executor.actor_id, "reason_codes": tuple(sorted(set(reasons))),
            "check_results": check_results, "signature_algorithm": "HMAC-SHA256",
            "key_id": self._key_id,
        }
        digest = "sha256:" + hashlib.sha256(canonical_json(base).encode("utf-8")).hexdigest()
        signature = hmac.new(self._key, digest.encode("ascii"), hashlib.sha256).hexdigest()
        return PromotionDecision(**base, decision_hash=digest, signature=signature)

    @staticmethod
    def _validate_approval(
        request: PromotionRequest, approval: HumanApproval, now: datetime, reasons: list[str]
    ) -> None:
        if not approval.approved:
            reasons.append("HUMAN_APPROVAL_REJECTED")
        if approval.tenant_id != request.tenant_id:
            reasons.append("APPROVAL_TENANT_MISMATCH")
        if approval.unit_id != request.unit_id or approval.revision_id != request.revision_id:
            reasons.append("APPROVAL_TARGET_MISMATCH")
        if approval.snapshot_hash != request.snapshot_hash:
            reasons.append("APPROVAL_SNAPSHOT_MISMATCH")
        if approval.policy_version != request.policy_version:
            reasons.append("APPROVAL_POLICY_MISMATCH")
        if approval.expires_at is not None and approval.expires_at <= now:
            reasons.append("HUMAN_APPROVAL_EXPIRED")
        if approval.approver.tenant_id != request.tenant_id:
            reasons.append("APPROVER_TENANT_MISMATCH")
        if approval.approver.actor_id in {request.submitter.actor_id, request.executor.actor_id}:
            reasons.append("HUMAN_APPROVER_NOT_SEPARATED")
        if not approval.signature.strip():
            reasons.append("HUMAN_APPROVAL_UNSIGNED")


__all__ = [
    "Actor", "ActorType", "CheckResult", "HardCheck", "HumanApproval", "POLICY_VERSION",
    "PromotionDecision", "PromotionGate", "PromotionGateError", "PromotionRequest",
    "REQUIRED_HARD_CHECKS", "RiskClass", "compute_snapshot_hash", "verify_signed_decision",
]
