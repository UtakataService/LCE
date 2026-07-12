"""Backend-neutral contract for Knowledge Unit repositories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable


class RepositoryError(RuntimeError):
    """Base error exposed by every repository backend."""


class ContractViolation(RepositoryError, ValueError):
    pass


class ConcurrencyConflict(RepositoryError):
    pass


class EvidenceNotFound(RepositoryError):
    pass


class PromotionRejected(RepositoryError):
    pass


class RepositoryUnavailable(RepositoryError):
    pass


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            raise ContractViolation("tenant_id is required")
        if self.tenant_id != self.tenant_id.strip():
            raise ContractViolation("tenant_id must not contain surrounding whitespace")


@dataclass(frozen=True, slots=True)
class CommandResult:
    revision: Any
    replayed: bool = False


REQUIRED_PROMOTION_CHECKS = frozenset(
    {"provenance", "license", "privacy", "contradiction", "regression"}
)


def validate_promotion(revision: Mapping[str, Any], decision: Any) -> None:
    """Apply the same fail-closed ACTIVE_L1 gate to every backend."""
    failures: list[str] = []
    scope = revision.get("scope") or {}
    if not any(value not in (None, "", [], {}, ()) for value in scope.values()):
        failures.append("scope is undefined")
    language = revision.get("language") or {}
    if language.get("identification_state") != "verified":
        failures.append("language is not verified")
    links = revision.get("evidence_links", revision.get("evidence", ())) or ()
    if not any(str(item.get("stance", "")).lower() == "supports" for item in links):
        failures.append("supporting evidence is absent")
    checks = revision.get("validation_decisions", revision.get("decisions", ())) or ()
    passed = {
        str(item.get("check_type")) for item in checks
        if str(item.get("result", "")).upper() == "PASS"
    }
    if isinstance(decision, Mapping) and isinstance(decision.get("checks"), Mapping):
        passed.update(str(name) for name, value in decision["checks"].items() if value is True or str(value).upper() == "PASS")
    missing = sorted(REQUIRED_PROMOTION_CHECKS - passed)
    if missing:
        failures.append("missing passed checks: " + ", ".join(missing))
    if any(
        str(item.get("result", "")).upper() != "PASS"
        and str(item.get("severity", "")).lower() in {"critical", "blocking"}
        for item in checks
    ):
        failures.append("blocking or unknown validation remains")
    promotion_pass = any(
        bool(item.get("promotion_decision"))
        and str(item.get("result", "")).upper() == "PASS"
        for item in checks
    ) or bool(isinstance(decision, Mapping) and decision.get("promotion_decision"))
    decision_pass = isinstance(decision, Mapping) and str(decision.get("result", "")).upper() == "PASS"
    if not (promotion_pass and decision_pass):
        failures.append("explicit passed promotion decision is absent")
    if failures:
        raise PromotionRejected("ACTIVE_L1 gate failed: " + "; ".join(failures))


@runtime_checkable
class KnowledgeUnitRepository(Protocol):
    tenant: TenantContext

    def create_observation(self, draft: Any, *, actor: Any, idempotency_key: str) -> Any: ...
    def revise(self, logical_id: Any, patch: Any, reason: str, actor: Any,
               expected_revision_no: int, idempotency_key: str) -> Any: ...
    def put_evidence(self, evidence: Any, *, actor: Any, idempotency_key: str) -> Any: ...
    def attach_evidence(self, logical_id: Any, link: Any, actor: Any,
                        expected_revision_no: int, idempotency_key: str) -> Any: ...
    def transition(self, logical_id: Any, target_status: Any, *, decision: Any,
                   expected_revision_no: int, idempotency_key: str) -> Any: ...
    def get_current(self, logical_id: Any) -> Any: ...
    def get_revision(self, revision_id: Any) -> Any: ...
    def list_history(self, logical_id: Any) -> tuple[Any, ...]: ...


def require_tenant(value: str | TenantContext) -> TenantContext:
    return value if isinstance(value, TenantContext) else TenantContext(value)


__all__ = [
    "CommandResult", "ConcurrencyConflict", "ContractViolation", "EvidenceNotFound",
    "KnowledgeUnitRepository", "PromotionRejected", "RepositoryError",
    "RepositoryUnavailable", "REQUIRED_PROMOTION_CHECKS", "TenantContext",
    "require_tenant", "validate_promotion",
]
