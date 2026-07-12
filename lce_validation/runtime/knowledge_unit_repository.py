"""JSON facade implementing the backend-neutral Knowledge Unit contract."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .knowledge_unit_contract import (
    ConcurrencyConflict,
    EvidenceNotFound,
    KnowledgeUnitRepository,
    PromotionRejected,
    RepositoryUnavailable,
    TenantContext,
    require_tenant,
    validate_promotion,
)
from .knowledge_unit_json_repository import (
    JSONKnowledgeUnitRepository,
    ValidationError,
    VersionConflictError,
)


class AttrDict(dict):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _obj(value: Any) -> Any:
    if isinstance(value, dict):
        data = AttrDict({key: _obj(item) for key, item in value.items()})
        if "unit_id" in data:
            data.setdefault("logical_id", data["unit_id"])
        return data
    if isinstance(value, list):
        return tuple(_obj(item) for item in value)
    return value


class JsonKnowledgeUnitRepository:
    """Compatibility facade; tenant is mandatory and immutable per instance."""

    def __init__(self, path: str | Path, tenant_id: str = "default") -> None:
        self.path = Path(path)
        self.tenant = require_tenant(tenant_id)
        self.tenant_id = self.tenant.tenant_id
        self._repo = JSONKnowledgeUnitRepository(self.path)
        self._evidence: dict[str, dict[str, Any]] = {}

    def _command(self, values: dict[str, Any]) -> dict[str, Any]:
        supplied = values.get("tenant_id")
        if supplied is not None and supplied != self.tenant_id:
            raise ValueError("command tenant differs from repository tenant")
        values["tenant_id"] = self.tenant_id
        values.setdefault("reason_code", "api_command")
        values.setdefault("policy_version", "knowledge-unit/v1")
        return values

    def _call(self, function: Any, command: dict[str, Any]) -> Any:
        command = self._command(command)
        if command.get("target_status") == "ACTIVE_L1":
            decision = command.get("decision")
            if not isinstance(decision, dict) or str(decision.get("result", "")).upper() != "PASS":
                raise PromotionRejected("ACTIVE_L1 requires an explicit PASS decision")
        try:
            return _obj(function(command))
        except VersionConflictError as exc:
            raise ConcurrencyConflict(str(exc)) from exc
        except OSError as exc:
            raise RepositoryUnavailable(str(exc)) from exc
        except ValidationError as exc:
            if "ACTIVE_L1" in str(exc) or "transition" in str(exc):
                raise PromotionRejected(str(exc)) from exc
            raise

    def create_observation(self, draft: Any, *, actor: Any, idempotency_key: str) -> Any:
        data = asdict(draft) if is_dataclass(draft) else dict(draft)
        return self._call(self._repo.create_observation, {
            "draft": data, "actor": actor, "idempotency_key": idempotency_key,
        })

    def revise(self, logical_id: Any, patch: Any, reason: str, actor: Any,
               expected_revision_no: int, idempotency_key: str) -> Any:
        return self._call(self._repo.revise, {
            "unit_id": str(logical_id), "patch": patch, "reason": reason,
            "actor": actor, "expected_revision_no": expected_revision_no,
            "idempotency_key": idempotency_key,
        })

    def put_evidence(self, evidence: Any, *, actor: Any, idempotency_key: str) -> Any:
        row = asdict(evidence) if is_dataclass(evidence) else dict(evidence)
        row["tenant_id"] = self.tenant_id
        self._evidence[str(row["evidence_id"])] = row
        return evidence

    def attach_evidence(self, logical_id: Any, link: Any, actor: Any,
                        expected_revision_no: int, idempotency_key: str) -> Any:
        row = asdict(link) if is_dataclass(link) else dict(link)
        evidence = self._evidence.get(str(row["evidence_id"]))
        if evidence is None:
            raise EvidenceNotFound(str(row["evidence_id"]))
        return self._call(self._repo.append_evidence, {
            "unit_id": str(logical_id), "evidence": evidence, "link": row,
            "actor": actor, "expected_revision_no": expected_revision_no,
            "idempotency_key": idempotency_key,
        })

    def transition(self, logical_id: Any, target_status: Any, *, decision: Any,
                   expected_revision_no: int, idempotency_key: str) -> Any:
        target = getattr(target_status, "value", target_status)
        if target == "ACTIVE_L1":
            raise PromotionRejected("ACTIVE_L1 requires the dedicated promote API")
        return self._call(self._repo.transition, {
            "unit_id": str(logical_id), "target_status": target,
            "decision": decision,
            "actor": decision.get("actor", "validator") if isinstance(decision, dict) else "validator",
            "expected_revision_no": expected_revision_no,
            "idempotency_key": idempotency_key,
        })

    def promote(self, logical_id: Any, *, decision: Any, actor: Any,
                expected_revision_no: int, idempotency_key: str) -> Any:
        if actor is None or not str(actor).strip():
            raise PromotionRejected("promotion actor is required")
        if not isinstance(decision, dict):
            raise PromotionRejected("promotion decision must be a mapping")
        decision_actor = decision.get("actor")
        if decision_actor is not None and str(decision_actor) != str(actor):
            raise PromotionRejected("promotion actor differs from decision actor")
        current = self._repo.get_current(self.tenant_id, str(logical_id))
        if current is None:
            raise PromotionRejected("knowledge unit does not exist")
        signed_decision = dict(decision)
        signed_decision["actor"] = actor
        validate_promotion(current, signed_decision)
        return self._call(self._repo.transition, {
            "unit_id": str(logical_id), "target_status": "ACTIVE_L1",
            "decision": signed_decision, "actor": actor,
            "validation_decisions": [
                {"check_type": name, "result": "PASS" if value is True or str(value).upper() == "PASS" else str(value).upper()}
                for name, value in signed_decision.get("checks", {}).items()
            ] + [{"check_type": "promotion", "result": signed_decision.get("result", "UNKNOWN"), "promotion_decision": bool(signed_decision.get("promotion_decision"))}],
            "expected_revision_no": expected_revision_no,
            "idempotency_key": idempotency_key,
            "reason_code": "promote_active_l1",
        })

    def retract(self, logical_id: Any, reason: str, actor: Any,
                expected_revision_no: int, idempotency_key: str) -> Any:
        return self._call(self._repo.retract, {
            "unit_id": str(logical_id), "reason": reason, "actor": actor,
            "expected_revision_no": expected_revision_no,
            "idempotency_key": idempotency_key,
        })

    def get_current(self, logical_id: Any) -> Any:
        return _obj(self._repo.get_current(self.tenant_id, str(logical_id)))

    def get_revision(self, revision_id: Any) -> Any:
        return _obj(self._repo.get_revision(self.tenant_id, str(revision_id)))

    def list_history(self, logical_id: Any) -> tuple[Any, ...]:
        return tuple(_obj(item) for item in self._repo.list_history(self.tenant_id, str(logical_id)))

    def count(self) -> int:
        if not self.path.exists():
            return 0
        store = json.loads(self.path.read_text(encoding="utf-8"))
        return sum(1 for head in store["heads"].values() if head.get("tenant_id") == self.tenant_id)


class MySQLKnowledgeUnitRepositoryAdapter:
    """Typed contract facade for the tenant-bound MySQL implementation."""
    def __init__(self, connection_factory: Any, tenant_id: str) -> None:
        from .knowledge_unit_mysql_repository import MySQLKnowledgeUnitRepository
        self.tenant = require_tenant(tenant_id)
        self._repo = MySQLKnowledgeUnitRepository(connection_factory, self.tenant.tenant_id)

    def _wrap(self, fn, *args, **kwargs):
        from .knowledge_unit_mysql_repository import KnowledgeUnitConflictError, PromotionRejected as MyPromotion
        try: return _obj(fn(*args, **kwargs))
        except KnowledgeUnitConflictError as exc: raise ConcurrencyConflict(str(exc)) from exc
        except MyPromotion as exc: raise PromotionRejected(str(exc)) from exc

    def create_observation(self, draft, **kwargs):
        data=asdict(draft) if is_dataclass(draft) else dict(draft)
        return self._wrap(self._repo.create_observation,data,**kwargs)
    def revise(self,*args,**kwargs): return self._wrap(self._repo.revise,*args,**kwargs)
    def put_evidence(self,*args,**kwargs): return self._wrap(self._repo.put_evidence,*args,**kwargs)
    def attach_evidence(self,*args,**kwargs): return self._wrap(self._repo.attach_evidence,*args,**kwargs)
    def transition(self,*args,**kwargs): return self._wrap(self._repo.transition,*args,**kwargs)
    def promote(self,*args,**kwargs): return self._wrap(self._repo.promote,*args,**kwargs)
    def retract(self,*args,**kwargs): return self._wrap(self._repo.retract,*args,**kwargs)
    def get_current(self,*args,**kwargs): return self._wrap(self._repo.get_current,*args,**kwargs)
    def get_revision(self,*args,**kwargs): return self._wrap(self._repo.get_revision,*args,**kwargs)
    def list_history(self,*args,**kwargs): return tuple(self._wrap(self._repo.list_history,*args,**kwargs))


assert isinstance(JsonKnowledgeUnitRepository, type)

__all__ = [
    "ConcurrencyConflict", "EvidenceNotFound", "JsonKnowledgeUnitRepository",
    "KnowledgeUnitRepository", "MySQLKnowledgeUnitRepositoryAdapter", "PromotionRejected", "RepositoryUnavailable", "TenantContext",
]
