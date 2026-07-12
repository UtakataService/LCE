from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
import unicodedata
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "lce.knowledge-repository.v2"
ACTIVE_STATES = frozenset({"ACTIVE_L1", "ACTIVE_L2", "ACTIVE_L3"})
TERMINAL_STATES = frozenset({"SUPERSEDED", "RETRACTED", "EXPIRED"})
ALLOWED_TRANSITIONS = {
    "OBSERVED": {"QUARANTINED", "RETRACTED"},
    "QUARANTINED": {"NORMALIZED", "REJECTED", "RETRACTED"},
    "NORMALIZED": {"LINKED", "REJECTED", "RETRACTED"},
    "LINKED": {"VERIFIED", "DISPUTED", "REJECTED", "RETRACTED"},
    "VERIFIED": {"SHADOW", "DISPUTED", "REJECTED", "RETRACTED"},
    "SHADOW": {"ACTIVE_L1", "DISPUTED", "EXPIRED", "RETRACTED"},
    "ACTIVE_L1": {"DISPUTED", "SUPERSEDED", "RETRACTED", "EXPIRED"},
    "DISPUTED": {"VERIFIED", "REJECTED"},
    "REJECTED": set(),
    "SUPERSEDED": set(),
    "RETRACTED": set(),
    "EXPIRED": set(),
}


class KnowledgeRepositoryError(RuntimeError):
    pass


class ValidationError(KnowledgeRepositoryError):
    pass


class VersionConflictError(KnowledgeRepositoryError):
    pass


class NotFoundError(KnowledgeRepositoryError):
    pass


class IdempotencyConflictError(KnowledgeRepositoryError):
    pass


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not key.startswith("_")}
    raise ValidationError(f"command/query must be mapping-like, got {type(value).__name__}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _new_id() -> str:
    return str(uuid.uuid4())


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _required(data: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = data.get(name)
        if value is not None and value != "":
            return value
    raise ValidationError(f"required field missing: {'/'.join(names)}")


def _parse_time(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _scope_defined(scope: Any) -> bool:
    if not isinstance(scope, Mapping) or not scope:
        return False
    return any(value not in (None, "", [], {}, "unknown") for value in scope.values())


class JSONKnowledgeUnitRepository:
    """Append-only Knowledge Unit reference repository backed by canonical JSON.

    Revisions, evidence and events are immutable records. Every mutation builds a
    complete next snapshot and atomically replaces the previous file; a failed
    write never advances a head. The implementation deliberately has no backend
    fallback.
    """

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._atomic_write(self._empty_store())
        else:
            self._validate_store(self._load())

    @staticmethod
    def _empty_store() -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generation": 0,
            "heads": {},
            "revisions": {},
            "evidence": {},
            "events": [],
            "idempotency": {},
        }

    def _load(self) -> dict[str, Any]:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise KnowledgeRepositoryError(f"cannot load repository: {exc}") from exc
        self._validate_store(value)
        return value

    @staticmethod
    def _validate_store(store: Any) -> None:
        if not isinstance(store, dict) or store.get("schema_version") != SCHEMA_VERSION:
            raise ValidationError("unsupported or malformed repository schema")
        for key, expected in (("heads", dict), ("revisions", dict), ("evidence", dict), ("events", list), ("idempotency", dict)):
            if not isinstance(store.get(key), expected):
                raise ValidationError(f"malformed repository collection: {key}")
        for unit_id, head in store["heads"].items():
            revision = store["revisions"].get(head.get("current_revision_id"))
            if revision is None or revision.get("unit_id") != unit_id:
                raise ValidationError(f"dangling head: {unit_id}")
            if revision.get("revision_no") != head.get("head_revision_no"):
                raise ValidationError(f"head revision mismatch: {unit_id}")

    def _atomic_write(self, store: dict[str, Any]) -> None:
        payload = _canonical_bytes(store) + b"\n"
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def _tenant_key(tenant_id: str, identifier: str) -> str:
        return f"{tenant_id}\x1f{identifier}"

    def _idempotent_result(self, store: dict[str, Any], tenant_id: str, key: str, command: dict[str, Any]) -> dict[str, Any] | None:
        record = store["idempotency"].get(self._tenant_key(tenant_id, key))
        if record is None:
            return None
        if record["command_hash"] != _fingerprint(command):
            raise IdempotencyConflictError(f"idempotency key reused with different command: {key}")
        revision = store["revisions"].get(record["revision_id"])
        if revision is None:
            raise ValidationError("idempotency ledger points to missing revision")
        return copy.deepcopy(revision)

    @staticmethod
    def _record_idempotency(store: dict[str, Any], tenant_id: str, key: str, command: dict[str, Any], revision_id: str) -> None:
        store["idempotency"][f"{tenant_id}\x1f{key}"] = {
            "command_hash": _fingerprint(command),
            "revision_id": revision_id,
        }

    @staticmethod
    def _head(store: dict[str, Any], tenant_id: str, unit_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        head = store["heads"].get(unit_id)
        if head is None or head.get("tenant_id") != tenant_id:
            raise NotFoundError(f"knowledge unit not found: {unit_id}")
        return head, store["revisions"][head["current_revision_id"]]

    @staticmethod
    def _check_version(head: Mapping[str, Any], command: Mapping[str, Any]) -> None:
        expected = _required(command, "expected_revision_no", "expected_version")
        if isinstance(expected, bool) or int(expected) != head["head_revision_no"]:
            raise VersionConflictError(f"expected revision {expected}, current is {head['head_revision_no']}")

    @staticmethod
    def _append_event(store: dict[str, Any], revision: Mapping[str, Any], command: Mapping[str, Any], event_type: str, from_status: str | None) -> None:
        store["events"].append({
            "event_id": str(command.get("event_id") or _new_id()),
            "unit_id": revision["unit_id"],
            "revision_id": revision["revision_id"],
            "event_type": event_type,
            "from_status": from_status,
            "to_status": revision["status"],
            "actor": copy.deepcopy(_required(command, "actor")),
            "reason_code": str(_required(command, "reason_code", "reason")),
            "policy_version": str(command.get("policy_version") or "unspecified"),
            "idempotency_key": str(_required(command, "idempotency_key")),
            "payload": copy.deepcopy(command.get("event_payload", {})),
            "occurred_at": str(command.get("occurred_at") or _now()),
        })

    @staticmethod
    def _claim_from(command: Mapping[str, Any]) -> dict[str, Any]:
        draft = command.get("draft") if isinstance(command.get("draft"), Mapping) else command
        claim = draft.get("claim") if isinstance(draft.get("claim"), Mapping) else draft
        return {
            "subject_ref": str(_required(claim, "subject_ref", "subject")),
            "predicate_ref": str(_required(claim, "predicate_ref", "predicate")),
            "object_kind": str(claim.get("object_kind") or "text_literal"),
            "object": copy.deepcopy(_required(claim, "object", "object_json")),
            "polarity": str(claim.get("polarity") or "positive"),
            "modality": str(claim.get("modality") or "asserted"),
        }

    def create_observation(self, command: Any) -> dict[str, Any]:
        data = _plain(command)
        tenant_id = str(_required(data, "tenant_id"))
        idempotency_key = str(_required(data, "idempotency_key"))
        with self._lock:
            store = self._load()
            previous = self._idempotent_result(store, tenant_id, idempotency_key, data)
            if previous is not None:
                return previous
            unit_id = str(data.get("unit_id") or data.get("logical_id") or _new_id())
            if unit_id in store["heads"]:
                raise ValidationError(f"knowledge unit already exists: {unit_id}")
            revision_id = str(data.get("revision_id") or _new_id())
            if revision_id in store["revisions"]:
                raise ValidationError(f"revision already exists: {revision_id}")
            draft = data.get("draft") if isinstance(data.get("draft"), Mapping) else data
            valid_from = draft.get("valid_from")
            valid_to = draft.get("valid_to")
            if _parse_time(valid_from) and _parse_time(valid_to) and _parse_time(valid_to) < _parse_time(valid_from):
                raise ValidationError("valid_to precedes valid_from")
            recorded_at = str(data.get("recorded_at") or _now())
            revision = {
                "revision_id": revision_id,
                "unit_id": unit_id,
                "tenant_id": tenant_id,
                "revision_no": 1,
                "predecessor_revision_id": None,
                "status": "OBSERVED",
                "claim": self._claim_from(data),
                "scope": copy.deepcopy(draft.get("scope") or {"state": "unknown"}),
                "language": copy.deepcopy(draft.get("language") or {"expression_language": draft.get("language_tag", "und"), "identification_state": "unknown"}),
                "valid_from": valid_from,
                "valid_to": valid_to,
                "recorded_at": recorded_at,
                "superseded_at": None,
                "schema_version": str(draft.get("schema_version") or SCHEMA_VERSION),
                "evidence_links": [],
                "validation_decisions": copy.deepcopy(draft.get("validation_decisions", [])),
                "metadata": copy.deepcopy(draft.get("metadata", {})),
            }
            revision["canonical_hash"] = _fingerprint({key: value for key, value in revision.items() if key != "canonical_hash"})
            next_store = copy.deepcopy(store)
            next_store["revisions"][revision_id] = revision
            next_store["heads"][unit_id] = {"tenant_id": tenant_id, "current_revision_id": revision_id, "head_revision_no": 1, "created_at": recorded_at}
            self._append_event(next_store, revision, data, "OBSERVATION_CREATED", None)
            self._record_idempotency(next_store, tenant_id, idempotency_key, data, revision_id)
            next_store["generation"] += 1
            self._atomic_write(next_store)
            return copy.deepcopy(revision)

    def _new_revision(self, store: dict[str, Any], tenant_id: str, unit_id: str, command: dict[str, Any], mutate: Any, event_type: str) -> dict[str, Any]:
        key = str(_required(command, "idempotency_key"))
        previous = self._idempotent_result(store, tenant_id, key, command)
        if previous is not None:
            return previous
        head, current = self._head(store, tenant_id, unit_id)
        self._check_version(head, command)
        revision = copy.deepcopy(current)
        revision["revision_id"] = str(command.get("revision_id") or _new_id())
        if revision["revision_id"] in store["revisions"]:
            raise ValidationError(f"revision already exists: {revision['revision_id']}")
        revision["revision_no"] = head["head_revision_no"] + 1
        revision["predecessor_revision_id"] = current["revision_id"]
        revision["recorded_at"] = str(command.get("recorded_at") or _now())
        revision["superseded_at"] = None
        mutate(revision, current)
        revision["canonical_hash"] = _fingerprint({key: value for key, value in revision.items() if key != "canonical_hash"})
        store["revisions"][revision["revision_id"]] = revision
        head["current_revision_id"] = revision["revision_id"]
        head["head_revision_no"] = revision["revision_no"]
        self._append_event(store, revision, command, event_type, current["status"])
        self._record_idempotency(store, tenant_id, key, command, revision["revision_id"])
        store["generation"] += 1
        return revision

    def append_evidence(self, command: Any) -> dict[str, Any]:
        data = _plain(command)
        tenant_id = str(_required(data, "tenant_id"))
        unit_id = str(_required(data, "unit_id", "logical_id"))
        evidence = copy.deepcopy(_required(data, "evidence"))
        if not isinstance(evidence, Mapping):
            evidence = _plain(evidence)
        evidence = dict(evidence)
        evidence_id = str(evidence.get("evidence_id") or data.get("evidence_id") or _new_id())
        evidence["evidence_id"] = evidence_id
        evidence["tenant_id"] = tenant_id
        link = copy.deepcopy(data.get("link") or {})
        link.setdefault("evidence_id", evidence_id)
        link.setdefault("stance", data.get("stance", "unresolved"))
        if link["stance"] not in {"supports", "contradicts", "limits_scope", "neutral", "unresolved"}:
            raise ValidationError(f"invalid evidence stance: {link['stance']}")
        with self._lock:
            store = self._load()
            existing = store["evidence"].get(evidence_id)
            if existing is not None and _fingerprint(existing) != _fingerprint(evidence):
                raise ValidationError(f"immutable evidence differs: {evidence_id}")
            def mutate(revision: dict[str, Any], _current: dict[str, Any]) -> None:
                if any(item["evidence_id"] == evidence_id and item.get("stance") == link["stance"] for item in revision["evidence_links"]):
                    raise ValidationError("evidence link already exists")
                revision["evidence_links"].append(link)
            next_store = copy.deepcopy(store)
            next_store["evidence"].setdefault(evidence_id, evidence)
            revision = self._new_revision(next_store, tenant_id, unit_id, data, mutate, "EVIDENCE_APPENDED")
            self._atomic_write(next_store)
            return copy.deepcopy(revision)

    attach_evidence = append_evidence

    def revise(self, command: Any) -> dict[str, Any]:
        data = _plain(command)
        tenant_id = str(_required(data, "tenant_id"))
        unit_id = str(_required(data, "unit_id", "logical_id"))
        patch = copy.deepcopy(_required(data, "patch"))
        allowed = {"claim", "scope", "language", "valid_from", "valid_to", "metadata", "validation_decisions"}
        unknown = set(patch) - allowed
        if unknown:
            raise ValidationError(f"revision patch contains protected fields: {sorted(unknown)}")
        def mutate(revision: dict[str, Any], current: dict[str, Any]) -> None:
            if current["status"] in TERMINAL_STATES:
                revision["status"] = "QUARANTINED"
            for key, value in patch.items():
                revision[key] = copy.deepcopy(value)
            if _parse_time(revision.get("valid_from")) and _parse_time(revision.get("valid_to")) and _parse_time(revision["valid_to"]) < _parse_time(revision["valid_from"]):
                raise ValidationError("valid_to precedes valid_from")
        with self._lock:
            next_store = copy.deepcopy(self._load())
            revision = self._new_revision(next_store, tenant_id, unit_id, data, mutate, "KNOWLEDGE_REVISED")
            self._atomic_write(next_store)
            return copy.deepcopy(revision)

    def transition(self, command: Any) -> dict[str, Any]:
        data = _plain(command)
        tenant_id = str(_required(data, "tenant_id"))
        unit_id = str(_required(data, "unit_id", "logical_id"))
        target = str(_required(data, "target_status", "to_status"))
        decision = data.get("decision")
        def mutate(revision: dict[str, Any], current: dict[str, Any]) -> None:
            if target not in ALLOWED_TRANSITIONS.get(current["status"], set()):
                raise ValidationError(f"invalid transition: {current['status']} -> {target}")
            if target == "ACTIVE_L1":
                supporting = any(link.get("stance") == "supports" for link in current["evidence_links"])
                checks = data.get("validation_decisions", current.get("validation_decisions", []))
                if not supporting or not _scope_defined(current.get("scope")) or not decision or not checks:
                    raise ValidationError("ACTIVE_L1 requires scope, supporting evidence, validation decisions and promotion decision")
                revision["validation_decisions"] = copy.deepcopy(checks)
            revision["status"] = target
            if decision is not None:
                revision.setdefault("metadata", {})["last_transition_decision"] = copy.deepcopy(decision)
        with self._lock:
            next_store = copy.deepcopy(self._load())
            revision = self._new_revision(next_store, tenant_id, unit_id, data, mutate, "STATUS_TRANSITIONED")
            self._atomic_write(next_store)
            return copy.deepcopy(revision)

    def retract(self, command: Any) -> dict[str, Any]:
        data = _plain(command)
        data["target_status"] = "RETRACTED"
        return self.transition(data)

    def get_revision(self, tenant_id: str, revision_id: str) -> dict[str, Any]:
        with self._lock:
            revision = self._load()["revisions"].get(str(revision_id))
            if revision is None or revision.get("tenant_id") != str(tenant_id):
                raise NotFoundError(f"revision not found: {revision_id}")
            return copy.deepcopy(revision)

    def get_current(self, tenant_id: str, unit_id: str) -> dict[str, Any] | None:
        with self._lock:
            store = self._load()
            head = store["heads"].get(str(unit_id))
            if head is None or head.get("tenant_id") != str(tenant_id):
                return None
            return copy.deepcopy(store["revisions"][head["current_revision_id"]])

    def list_history(self, tenant_id: str, unit_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            revisions = [
                copy.deepcopy(item) for item in self._load()["revisions"].values()
                if item.get("tenant_id") == str(tenant_id) and item.get("unit_id") == str(unit_id)
            ]
        revisions.sort(key=lambda item: item["revision_no"])
        return tuple(revisions)

    @staticmethod
    def _matches(revision: Mapping[str, Any], query: Mapping[str, Any], *, inference: bool) -> bool:
        if revision.get("tenant_id") != str(query.get("tenant_id")):
            return False
        statuses = ACTIVE_STATES if inference else set(query.get("statuses") or ALLOWED_TRANSITIONS)
        if revision.get("status") not in statuses:
            return False
        as_of = _parse_time(query.get("as_of") or query.get("as_of_valid_time") or _now())
        valid_from, valid_to = _parse_time(revision.get("valid_from")), _parse_time(revision.get("valid_to"))
        if valid_from and as_of < valid_from or valid_to and as_of >= valid_to:
            return False
        language = query.get("language_tag") or query.get("language")
        stored_language = revision.get("language", {}).get("expression_language", "und")
        if language and stored_language != language:
            return False
        requested_scope = query.get("scope")
        if requested_scope:
            stored_scope = revision.get("scope") or {}
            if any(stored_scope.get(key) != value for key, value in requested_scope.items() if value is not None):
                return False
        claim = revision.get("claim", {})
        for query_key, claim_key in (("subject_ref", "subject_ref"), ("predicate_ref", "predicate_ref")):
            if query.get(query_key) is not None and claim.get(claim_key) != query[query_key]:
                return False
        text = query.get("text")
        if text:
            haystack = unicodedata.normalize("NFC", json.dumps(claim, ensure_ascii=False)).casefold()
            if unicodedata.normalize("NFC", str(text)).casefold() not in haystack:
                return False
        return True

    def search_for_inference(self, query: Any) -> tuple[dict[str, Any], ...]:
        data = _plain(query)
        _required(data, "tenant_id")
        with self._lock:
            store = self._load()
            rows = [store["revisions"][head["current_revision_id"]] for head in store["heads"].values()]
            result = [copy.deepcopy(row) for row in rows if self._matches(row, data, inference=True)]
        result.sort(key=lambda row: (row["unit_id"], row["revision_no"]))
        return tuple(result[: int(data.get("limit", 100))])

    def search_for_review(self, query: Any) -> tuple[dict[str, Any], ...]:
        data = _plain(query)
        _required(data, "tenant_id")
        with self._lock:
            store = self._load()
            rows = [store["revisions"][head["current_revision_id"]] for head in store["heads"].values()]
            result = [copy.deepcopy(row) for row in rows if self._matches(row, data, inference=False)]
        result.sort(key=lambda row: (row["unit_id"], row["revision_no"]))
        return tuple(result[: int(data.get("limit", 100))])

    def reconstruct_for_audit(self, query: Any) -> dict[str, Any]:
        data = _plain(query)
        tenant_id = str(_required(data, "tenant_id"))
        unit_id = str(_required(data, "unit_id", "logical_id"))
        with self._lock:
            store = self._load()
            history = [copy.deepcopy(row) for row in store["revisions"].values() if row.get("tenant_id") == tenant_id and row.get("unit_id") == unit_id]
            history.sort(key=lambda row: row["revision_no"])
            if not history:
                raise NotFoundError(f"knowledge unit not found: {unit_id}")
            revision_ids = {row["revision_id"] for row in history}
            events = [copy.deepcopy(event) for event in store["events"] if event.get("revision_id") in revision_ids]
            evidence_ids = {link["evidence_id"] for row in history for link in row.get("evidence_links", [])}
            evidence = [copy.deepcopy(store["evidence"][key]) for key in sorted(evidence_ids) if key in store["evidence"]]
            return {"unit_id": unit_id, "history": history, "events": events, "evidence": evidence, "generation": store["generation"]}

    # Explicit aliases retain typed entry points while easing the protocol's
    # final naming choice in the coordinating branch.
    inference_search = search_for_inference
    review_search = search_for_review
    audit_search = reconstruct_for_audit


KnowledgeUnitJSONRepository = JSONKnowledgeUnitRepository
