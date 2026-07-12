"""Domain types and invariants for versioned LCE Knowledge Units.

This module deliberately contains no persistence code.  JSON and SQL
repositories must both pass values through these constructors and validators.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
import math
import unicodedata
from typing import Any, Mapping, Sequence
from uuid import UUID


CANONICAL_SCHEMA_VERSION = "knowledge-unit/v1"


class KnowledgeUnitError(ValueError):
    """Base class for domain validation failures."""


class IntegrityViolation(KnowledgeUnitError):
    pass


class InvalidTransition(KnowledgeUnitError):
    pass


@dataclass(frozen=True)
class KnowledgeUnitDraft:
    claim: dict[str, Any]
    scope: dict[str, Any]
    language: dict[str, Any]


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    raw_text: str
    normalized_text: str
    source_uri: str
    content_hash: str
    license: str
    language: str


@dataclass(frozen=True)
class EvidenceLink:
    evidence_id: str
    stance: str
    source_ref: str


class Status(str, Enum):
    OBSERVED = "OBSERVED"
    QUARANTINED = "QUARANTINED"
    NORMALIZED = "NORMALIZED"
    LINKED = "LINKED"
    VERIFIED = "VERIFIED"
    SHADOW = "SHADOW"
    ACTIVE_L1 = "ACTIVE_L1"
    DISPUTED = "DISPUTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    RETRACTED = "RETRACTED"
    EXPIRED = "EXPIRED"


class Polarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class Modality(str, Enum):
    ASSERTED = "asserted"
    POSSIBLE = "possible"
    PROBABLE = "probable"
    REQUIRED = "required"
    PERMITTED = "permitted"
    REPORTED = "reported"


class ObjectKind(str, Enum):
    ENTITY_REF = "entity_ref"
    CONCEPT_REF = "concept_ref"
    SCALAR = "scalar"
    QUANTITY = "quantity"
    TEXT_LITERAL = "text_literal"


class EvidenceStance(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    LIMITS_SCOPE = "limits_scope"
    NEUTRAL = "neutral"
    UNRESOLVED = "unresolved"


class DecisionResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class AccessClass(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


@dataclass(frozen=True, slots=True)
class ClaimObject:
    kind: ObjectKind
    value: Any
    unit: str | None = None

    def __post_init__(self) -> None:
        if self.value is None:
            raise IntegrityViolation("claim object value is required")
        if self.kind is ObjectKind.QUANTITY and not self.unit:
            raise IntegrityViolation("quantity object requires a unit")


@dataclass(frozen=True, slots=True)
class Claim:
    subject_ref: str
    predicate_ref: str
    object: ClaimObject
    polarity: Polarity = Polarity.POSITIVE
    modality: Modality = Modality.ASSERTED

    def __post_init__(self) -> None:
        if not self.subject_ref.strip() or not self.predicate_ref.strip():
            raise IntegrityViolation("claim subject and predicate are required")


@dataclass(frozen=True, slots=True)
class Scope:
    domain: str | None = None
    jurisdiction: str | None = None
    location: str | None = None
    population: str | None = None
    language_variety: str | None = None
    modality: str | None = None
    context_constraints: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()

    @property
    def is_defined(self) -> bool:
        return any(
            value is not None and (not isinstance(value, str) or bool(value.strip()))
            for value in (
                self.domain,
                self.jurisdiction,
                self.location,
                self.population,
                self.language_variety,
                self.modality,
            )
        ) or bool(self.context_constraints or self.exclusions)


@dataclass(frozen=True, slots=True)
class Temporality:
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        for value in (self.valid_from, self.valid_to, self.recorded_at, self.superseded_at):
            if value is not None and value.tzinfo is None:
                raise IntegrityViolation("timestamps must be timezone-aware")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise IntegrityViolation("valid_to precedes valid_from")
        if self.superseded_at and self.superseded_at < self.recorded_at:
            raise IntegrityViolation("superseded_at precedes recorded_at")


@dataclass(frozen=True, slots=True)
class LanguageState:
    expression_language: str = "und"
    source_language: str = "und"
    semantic_anchor_language: str = "und"
    identification_state: str = "unknown"
    translation_status: str = "none"
    residual_notes: str | None = None

    def __post_init__(self) -> None:
        if self.identification_state not in {"unknown", "hypothesized", "verified"}:
            raise IntegrityViolation("invalid language identification state")
        if self.translation_status not in {"none", "candidate", "partial", "verified"}:
            raise IntegrityViolation("invalid translation status")
        for tag in (self.expression_language, self.source_language, self.semantic_anchor_language):
            if not tag or any(ch.isspace() for ch in tag):
                raise IntegrityViolation("language tags must be non-empty BCP 47-like values")


def _score(value: Decimal | float | int | None, name: str) -> Decimal | None:
    if value is None:
        return None
    result = Decimal(str(value))
    if not Decimal("0") <= result <= Decimal("1"):
        raise IntegrityViolation(f"{name} must be between 0 and 1")
    return result


@dataclass(frozen=True, slots=True)
class EvidenceRelation:
    evidence_id: UUID
    stance: EvidenceStance
    independence_group: str | None
    linked_by: str
    linked_at: datetime
    relevance: Decimal | None = None
    reliability: Decimal | None = None
    interpretation: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.linked_by.strip() or self.linked_at.tzinfo is None:
            raise IntegrityViolation("evidence link requires actor and aware timestamp")
        object.__setattr__(self, "relevance", _score(self.relevance, "relevance"))
        object.__setattr__(self, "reliability", _score(self.reliability, "reliability"))
        object.__setattr__(self, "interpretation", dict(self.interpretation))


@dataclass(frozen=True, slots=True)
class ValidationDecision:
    check_type: str
    result: DecisionResult
    severity: str
    policy_version: str
    checked_at: datetime
    findings: Mapping[str, Any] = field(default_factory=dict)
    promotion_decision: bool = False

    def __post_init__(self) -> None:
        if not all((self.check_type.strip(), self.severity.strip(), self.policy_version.strip())):
            raise IntegrityViolation("validation decision metadata is incomplete")
        if self.checked_at.tzinfo is None:
            raise IntegrityViolation("decision timestamp must be timezone-aware")
        object.__setattr__(self, "findings", dict(self.findings))


@dataclass(frozen=True, slots=True)
class KnowledgeRevision:
    unit_id: UUID
    revision_id: UUID
    revision_no: int
    predecessor_revision_id: UUID | None
    tenant_id: str
    status: Status
    claim: Claim
    scope: Scope
    temporality: Temporality
    language: LanguageState
    evidence: tuple[EvidenceRelation, ...] = ()
    decisions: tuple[ValidationDecision, ...] = ()
    access_class: AccessClass = AccessClass.INTERNAL
    schema_version: str = CANONICAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.revision_no < 1 or not self.tenant_id.strip():
            raise IntegrityViolation("positive revision number and tenant are required")
        if self.revision_no == 1 and self.predecessor_revision_id is not None:
            raise IntegrityViolation("first revision cannot have a predecessor")
        if self.revision_no > 1 and self.predecessor_revision_id is None:
            raise IntegrityViolation("later revision requires a predecessor")
        if len({(item.evidence_id, item.stance) for item in self.evidence}) != len(self.evidence):
            raise IntegrityViolation("duplicate evidence stance relation")

    @property
    def canonical_hash(self) -> str:
        return canonical_hash(self)


@dataclass(frozen=True, slots=True)
class TransitionCommand:
    tenant_id: str
    unit_id: UUID
    revision_id: UUID
    expected_revision_no: int
    target_status: Status
    actor: Mapping[str, Any]
    reason_code: str
    policy_version: str
    idempotency_key: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not self.actor or not all(
            value.strip() for value in (self.tenant_id, self.reason_code, self.policy_version, self.idempotency_key)
        ):
            raise IntegrityViolation("transition audit metadata is incomplete")
        if self.occurred_at.tzinfo is None:
            raise IntegrityViolation("transition timestamp must be timezone-aware")
        object.__setattr__(self, "actor", dict(self.actor))


_ALLOWED_TRANSITIONS: Mapping[Status, frozenset[Status]] = {
    Status.OBSERVED: frozenset({Status.QUARANTINED}),
    Status.QUARANTINED: frozenset({Status.NORMALIZED, Status.REJECTED}),
    Status.NORMALIZED: frozenset({Status.LINKED, Status.REJECTED}),
    Status.LINKED: frozenset({Status.VERIFIED, Status.REJECTED, Status.DISPUTED}),
    Status.VERIFIED: frozenset({Status.SHADOW, Status.REJECTED, Status.DISPUTED}),
    Status.SHADOW: frozenset({Status.ACTIVE_L1, Status.DISPUTED, Status.EXPIRED, Status.RETRACTED}),
    Status.ACTIVE_L1: frozenset({Status.DISPUTED, Status.SUPERSEDED, Status.RETRACTED, Status.EXPIRED}),
    Status.DISPUTED: frozenset({Status.VERIFIED, Status.REJECTED}),
}


_ACTIVE_REQUIRED_CHECKS = frozenset(
    {"provenance", "license", "privacy", "contradiction", "regression"}
)


def validate_transition(revision: KnowledgeRevision, command: TransitionCommand) -> None:
    """Reject a transition that violates lifecycle, concurrency, or promotion gates."""
    if command.tenant_id != revision.tenant_id or command.unit_id != revision.unit_id:
        raise IntegrityViolation("transition target does not match revision")
    if command.revision_id != revision.revision_id:
        raise IntegrityViolation("transition revision does not match current revision")
    if command.expected_revision_no != revision.revision_no:
        raise IntegrityViolation("expected revision number does not match current revision")
    if command.target_status not in _ALLOWED_TRANSITIONS.get(revision.status, frozenset()):
        raise InvalidTransition(f"{revision.status.value} -> {command.target_status.value} is not allowed")
    if command.target_status is Status.ACTIVE_L1:
        _validate_active_gate(revision)


def _validate_active_gate(revision: KnowledgeRevision) -> None:
    failures: list[str] = []
    if not revision.scope.is_defined:
        failures.append("scope is undefined")
    if revision.access_class is AccessClass.RESTRICTED:
        failures.append("access is restricted")
    supports = [item for item in revision.evidence if item.stance is EvidenceStance.SUPPORTS]
    if not supports:
        failures.append("supporting evidence is absent")
    if revision.language.identification_state != "verified":
        failures.append("language is not verified")
    passed = {
        item.check_type
        for item in revision.decisions
        if item.result is DecisionResult.PASS
    }
    missing = sorted(_ACTIVE_REQUIRED_CHECKS - passed)
    if missing:
        failures.append("missing passed checks: " + ", ".join(missing))
    if any(item.result is not DecisionResult.PASS and item.severity.lower() in {"critical", "blocking"}
           for item in revision.decisions):
        failures.append("blocking validation decision remains")
    if not any(item.promotion_decision and item.result is DecisionResult.PASS for item in revision.decisions):
        failures.append("promotion decision is absent")
    if failures:
        raise InvalidTransition("ACTIVE_L1 gate failed: " + "; ".join(failures))


@dataclass(frozen=True, slots=True)
class InferenceQuery:
    tenant_id: str
    text: str
    scope: Scope
    as_of_valid_time: datetime
    language_tag: str = "und"
    permission_labels: tuple[str, ...] = ()
    limit: int = 20

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.text.strip() or not self.scope.is_defined:
            raise IntegrityViolation("inference query requires tenant, text, and defined scope")
        if self.as_of_valid_time.tzinfo is None or not 1 <= self.limit <= 100:
            raise IntegrityViolation("invalid inference time or limit")


@dataclass(frozen=True, slots=True)
class ReviewQuery:
    tenant_id: str
    statuses: tuple[Status, ...] = ()
    language_tag: str | None = None
    cursor: str | None = None
    limit: int = 50

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not 1 <= self.limit <= 200:
            raise IntegrityViolation("invalid review query")


@dataclass(frozen=True, slots=True)
class AuditQuery:
    tenant_id: str
    unit_id: UUID
    as_of_record_time: datetime | None = None
    include_evidence: bool = True
    include_decisions: bool = True

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise IntegrityViolation("audit query tenant is required")
        if self.as_of_record_time is not None and self.as_of_record_time.tzinfo is None:
            raise IntegrityViolation("audit record time must be timezone-aware")


def _canonical_value(value: Any) -> Any:
    if is_dataclass(value):
        return _canonical_value(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise IntegrityViolation("canonical datetime must be timezone-aware")
        utc = value.astimezone(timezone.utc)
        return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise IntegrityViolation("canonical JSON forbids non-finite floats")
        return json.loads(json.dumps(value, allow_nan=False))
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (type(None), bool, int)):
        return value
    raise IntegrityViolation(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return deterministic UTF-8 JSON for a logical domain value."""
    return json.dumps(
        _canonical_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


__all__ = [
    "AccessClass", "AuditQuery", "CANONICAL_SCHEMA_VERSION", "Claim", "ClaimObject",
    "DecisionResult", "EvidenceRelation", "EvidenceStance", "InferenceQuery",
    "IntegrityViolation", "InvalidTransition", "KnowledgeRevision", "KnowledgeUnitError",
    "LanguageState", "Modality", "ObjectKind", "Polarity", "ReviewQuery", "Scope",
    "Status", "Temporality", "TransitionCommand", "ValidationDecision", "canonical_hash",
    "canonical_json", "validate_transition",
]
