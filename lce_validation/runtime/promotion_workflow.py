"""Fail-closed workflow for reviewing, promoting, and retracting knowledge.

The store in this module is an in-process reference implementation.  Its
transactions are protected by one lock; SQL implementations must preserve the
same ordering and atomicity with row locks and a transactional outbox.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
from threading import RLock
from typing import Any, Callable, Mapping
from uuid import uuid4

from .knowledge_unit_contract import (
    ContractViolation,
    KnowledgeUnitRepository,
    PromotionRejected,
    TenantContext,
    require_tenant,
    validate_promotion,
)
from .knowledge_unit import Status


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ReviewStatus(str, Enum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    IN_REVIEW = "IN_REVIEW"
    DECIDED_APPROVE = "DECIDED_APPROVE"
    DECIDED_REJECT = "DECIDED_REJECT"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    APPLIED = "APPLIED"
    STALE = "STALE"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class ReviewItem:
    review_id: str
    tenant_id: str
    logical_id: str
    revision_id: str
    revision_no: int
    validation_snapshot_hash: str
    policy_id: str
    policy_version: str
    risk_class: str = "normal"
    priority: int = 0
    status: ReviewStatus = ReviewStatus.QUEUED
    available_at: datetime = field(default_factory=_utcnow)
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    attempt_count: int = 0
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    decision_id: str
    review_id: str
    revision_id: str
    revision_no: int
    decision: str
    reviewer_id: str
    reviewer_role: str
    validation_snapshot_hash: str
    policy_id: str
    policy_version: str
    reason_codes: tuple[str, ...]
    idempotency_key: str
    decided_at: datetime = field(default_factory=_utcnow)
    signature: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    event_id: str
    tenant_id: str
    event_type: str
    aggregate_id: str
    generation: int
    payload: Mapping[str, Any]
    created_at: datetime = field(default_factory=_utcnow)


class ReviewNotFound(ContractViolation): pass
class ReviewLeased(ContractViolation): pass
class StaleReview(PromotionRejected): pass
class AuthorizationRejected(PromotionRejected): pass
class IdempotencyConflict(ContractViolation): pass


class PromotionWorkflow:
    """Tenant-bound reference workflow with atomic in-memory bookkeeping."""

    def __init__(
        self,
        repository: KnowledgeUnitRepository,
        tenant: str | TenantContext,
        *,
        signature_verifier: Callable[[PromotionDecision], bool] | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.repository = repository
        self.tenant = require_tenant(tenant)
        repo_tenant = getattr(repository, "tenant", None)
        if repo_tenant is not None and require_tenant(repo_tenant).tenant_id != self.tenant.tenant_id:
            raise ContractViolation("repository tenant differs from workflow tenant")
        self._verify_signature = signature_verifier or (lambda decision: decision.signature is not None)
        self._clock = clock
        self._lock = RLock()
        self._reviews: dict[str, ReviewItem] = {}
        self._review_keys: dict[tuple[str, str, str, str], str] = {}
        self._decisions: dict[str, PromotionDecision] = {}
        self._idempotency: dict[str, tuple[str, Any]] = {}
        self._outbox: list[OutboxEvent] = []
        self._generation = 0

    @property
    def generation(self) -> int:
        return self._generation

    def cache_key(self, query_contract_version: str, normalized_query_hash: str) -> str:
        return f"{self.tenant.tenant_id}/{self._generation}/{query_contract_version}/{normalized_query_hash}"

    def outbox(self) -> tuple[OutboxEvent, ...]:
        return tuple(self._outbox)

    def enqueue(self, logical_id: str, validation_snapshot: Mapping[str, Any], *,
                policy_id: str, policy_version: str, risk_class: str = "normal",
                priority: int = 0) -> ReviewItem:
        with self._lock:
            revision = self.repository.get_current(logical_id)
            if revision is None or str(_value(revision, "status")) not in {"SHADOW", "Status.SHADOW"}:
                raise PromotionRejected("only the current SHADOW revision can be queued")
            revision_id = str(_value(revision, "revision_id"))
            revision_no = int(_value(revision, "revision_no"))
            snapshot_hash = _canonical_hash(validation_snapshot)
            key = (revision_id, policy_version, snapshot_hash, self.tenant.tenant_id)
            existing = self._review_keys.get(key)
            if existing:
                return self._reviews[existing]
            now = self._clock()
            item = ReviewItem(str(uuid4()), self.tenant.tenant_id, str(logical_id), revision_id,
                              revision_no, snapshot_hash, policy_id, policy_version,
                              risk_class, priority, created_at=now, updated_at=now)
            self._reviews[item.review_id] = item
            self._review_keys[key] = item.review_id
            return item

    def claim(self, review_id: str, owner: str, *, lease_seconds: int = 300) -> ReviewItem:
        if not owner or lease_seconds <= 0:
            raise ContractViolation("owner and a positive lease are required")
        with self._lock:
            item = self._get(review_id)
            now = self._clock()
            active = item.lease_expires_at is not None and item.lease_expires_at > now
            if active and item.lease_owner != owner:
                raise ReviewLeased("review is leased by another reviewer")
            if item.status not in {ReviewStatus.QUEUED, ReviewStatus.CLAIMED, ReviewStatus.IN_REVIEW}:
                raise ContractViolation("review cannot be claimed in its current state")
            item = replace(item, status=ReviewStatus.CLAIMED, lease_owner=owner,
                           lease_expires_at=now + timedelta(seconds=lease_seconds),
                           attempt_count=item.attempt_count + (0 if active else 1), updated_at=now)
            self._reviews[review_id] = item
            return item

    def release(self, review_id: str, owner: str) -> ReviewItem:
        with self._lock:
            item = self._owned(self._get(review_id), owner)
            item = replace(item, status=ReviewStatus.QUEUED, lease_owner=None,
                           lease_expires_at=None, updated_at=self._clock())
            self._reviews[review_id] = item
            return item

    def approve(self, review_id: str, decision: PromotionDecision, *, submitter_id: str | None = None) -> Any:
        """Verify and atomically apply an approval through the repository gate."""
        with self._lock:
            item = self._owned(self._get(review_id), decision.reviewer_id)
            digest = _canonical_hash(decision)
            replay = self._idempotency.get(decision.idempotency_key)
            if replay:
                if replay[0] != digest:
                    raise IdempotencyConflict("idempotency key was reused with different content")
                return replay[1]
            if submitter_id and submitter_id == decision.reviewer_id:
                raise AuthorizationRejected("submitter cannot approve their own knowledge")
            if decision.reviewer_role not in {"reviewer", "senior_reviewer"}:
                raise AuthorizationRejected("reviewer role is not authorized")
            if item.risk_class in {"high", "critical"} and decision.reviewer_role != "senior_reviewer":
                raise AuthorizationRejected("high-risk approval requires a senior reviewer")
            if not self._verify_signature(decision):
                raise AuthorizationRejected("decision signature is invalid")
            self._match(item, decision)
            current = self.repository.get_current(item.logical_id)
            if current is None or str(_value(current, "revision_id")) != item.revision_id:
                self._mark_stale(item)
                raise StaleReview("knowledge head changed during review")
            if int(_value(current, "revision_no")) != item.revision_no:
                self._mark_stale(item)
                raise StaleReview("knowledge revision changed during review")
            decision_map = {"result": "PASS", "actor": "promotion_service",
                            "decision_id": decision.decision_id,
                            "validation_snapshot_hash": decision.validation_snapshot_hash}
            validate_promotion(current, decision_map)
            result = self.repository.transition(
                item.logical_id, Status.ACTIVE_L1, decision=decision_map,
                expected_revision_no=item.revision_no,
                idempotency_key=decision.idempotency_key,
            )
            self._decisions[decision.decision_id] = decision
            self._generation += 1
            event = self._event("knowledge.promoted.v1", item.logical_id, {
                "review_id": item.review_id, "decision_id": decision.decision_id,
                "revision_id": str(_value(result, "revision_id", item.revision_id)),
                "status": "ACTIVE_L1",
            })
            self._outbox.append(event)
            self._reviews[review_id] = replace(item, status=ReviewStatus.APPLIED,
                                               lease_owner=None, lease_expires_at=None,
                                               updated_at=self._clock())
            self._idempotency[decision.idempotency_key] = (digest, result)
            return result

    def retract(self, logical_id: str, *, actor_id: str, actor_role: str, reason: str,
                expected_revision_no: int, idempotency_key: str, emergency: bool = False) -> Any:
        if not reason.strip():
            raise ContractViolation("retraction reason is required")
        allowed = {"senior_reviewer", "emergency_retractor"} if emergency else {"reviewer", "senior_reviewer"}
        if actor_role not in allowed:
            raise AuthorizationRejected("actor is not authorized to retract knowledge")
        payload = {"logical_id": logical_id, "actor_id": actor_id, "actor_role": actor_role,
                   "reason": reason, "expected_revision_no": expected_revision_no, "emergency": emergency}
        digest = _canonical_hash(payload)
        with self._lock:
            replay = self._idempotency.get(idempotency_key)
            if replay:
                if replay[0] != digest:
                    raise IdempotencyConflict("idempotency key was reused with different content")
                return replay[1]
            result = self.repository.retract(logical_id, reason, actor_id,
                                             expected_revision_no, idempotency_key)
            self._generation += 1
            self._outbox.append(self._event("knowledge.retracted.v1", logical_id, {
                "reason": reason, "actor_id": actor_id, "emergency": emergency,
                "revision_id": str(_value(result, "revision_id", "")),
            }))
            self._invalidate_reviews(logical_id)
            self._idempotency[idempotency_key] = (digest, result)
            return result

    def invalidate_reviews(self, logical_id: str) -> int:
        with self._lock:
            return self._invalidate_reviews(logical_id)

    def get_review(self, review_id: str) -> ReviewItem:
        return self._get(review_id)

    def _get(self, review_id: str) -> ReviewItem:
        try:
            return self._reviews[review_id]
        except KeyError as exc:
            raise ReviewNotFound(review_id) from exc

    def _owned(self, item: ReviewItem, owner: str) -> ReviewItem:
        now = self._clock()
        if item.lease_owner != owner or item.lease_expires_at is None or item.lease_expires_at <= now:
            raise ReviewLeased("an active lease owned by the reviewer is required")
        return item

    @staticmethod
    def _match(item: ReviewItem, decision: PromotionDecision) -> None:
        if decision.review_id != item.review_id or decision.revision_id != item.revision_id:
            raise StaleReview("decision targets another review or revision")
        if decision.revision_no != item.revision_no:
            raise StaleReview("decision revision number is stale")
        if decision.validation_snapshot_hash != item.validation_snapshot_hash:
            raise StaleReview("validation snapshot changed")
        if decision.policy_id != item.policy_id or decision.policy_version != item.policy_version:
            raise StaleReview("promotion policy changed")
        if decision.decision.upper() != "APPROVE":
            raise PromotionRejected("approve command requires an APPROVE decision")

    def _mark_stale(self, item: ReviewItem) -> None:
        self._reviews[item.review_id] = replace(item, status=ReviewStatus.STALE,
                                                lease_owner=None, lease_expires_at=None,
                                                updated_at=self._clock())

    def _invalidate_reviews(self, logical_id: str) -> int:
        changed = 0
        terminal = {ReviewStatus.APPLIED, ReviewStatus.STALE, ReviewStatus.CANCELLED}
        for review_id, item in tuple(self._reviews.items()):
            if item.logical_id == logical_id and item.status not in terminal:
                self._reviews[review_id] = replace(item, status=ReviewStatus.STALE,
                                                   lease_owner=None, lease_expires_at=None,
                                                   updated_at=self._clock())
                changed += 1
        if changed:
            self._outbox.append(self._event("promotion.review_stale.v1", logical_id, {"count": changed}))
        return changed

    def _event(self, event_type: str, logical_id: str, payload: Mapping[str, Any]) -> OutboxEvent:
        return OutboxEvent(str(uuid4()), self.tenant.tenant_id, event_type, logical_id,
                           self._generation, dict(payload), self._clock())


__all__ = [
    "AuthorizationRejected", "IdempotencyConflict", "OutboxEvent", "PromotionDecision",
    "PromotionWorkflow", "ReviewItem", "ReviewLeased", "ReviewNotFound", "ReviewStatus",
    "StaleReview",
]
