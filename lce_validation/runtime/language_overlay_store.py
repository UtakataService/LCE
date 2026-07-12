from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


SCHEMA_VERSION = "session-language-overlay.v1"
OVERLAY_STATES = frozenset(
    {
        "detected",
        "segment_candidate",
        "association_candidate",
        "babbling_safe",
        "discriminating",
        "provisional_use",
        "verified_usage",
        "consolidated",
        "retracted",
    }
)
ENTRY_STATES = frozenset({"candidate", "verified", "suppressed", "retracted"})


class OverlayStoreError(RuntimeError):
    """Base error for language overlay persistence."""


class OverlayNotFoundError(OverlayStoreError):
    pass


class OverlayConflictError(OverlayStoreError):
    pass


class OverlayValidationError(OverlayStoreError, ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("invalid language overlay: " + "; ".join(errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_overlay(
    overlay_id: str,
    *,
    session_id: str,
    source_language: str = "und",
    script_hypotheses: list[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an unpersisted, schema-valid session language overlay."""
    now = utc_now()
    overlay = {
        "schema_version": SCHEMA_VERSION,
        "overlay_id": overlay_id,
        "session_id": session_id,
        "source_language": source_language or "und",
        "script_hypotheses": list(script_hypotheses or []),
        "version": 0,
        "state": "detected",
        "created_at": now,
        "updated_at": now,
        "entries": {},
        "evidence": [],
        "correction_history": [],
        "state_history": [{"from": None, "to": "detected", "at": now, "reason": "created"}],
        "retraction": None,
        "metadata": dict(metadata or {}),
    }
    validate_overlay(overlay)
    return overlay


def validate_overlay(overlay: Mapping[str, Any]) -> None:
    """Validate the persisted contract without coercing or dropping fields."""
    errors: list[str] = []
    required = {
        "schema_version",
        "overlay_id",
        "session_id",
        "source_language",
        "version",
        "state",
        "created_at",
        "updated_at",
        "entries",
        "evidence",
        "correction_history",
        "state_history",
        "retraction",
    }
    for key in sorted(required - set(overlay)):
        errors.append(f"missing:{key}")
    if overlay.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported:schema_version")
    for key in ("overlay_id", "session_id", "source_language", "created_at", "updated_at"):
        if not isinstance(overlay.get(key), str) or not overlay.get(key, "").strip():
            errors.append(f"invalid:{key}")
    if not isinstance(overlay.get("version"), int) or isinstance(overlay.get("version"), bool) or overlay.get("version", -1) < 0:
        errors.append("invalid:version")
    if overlay.get("state") not in OVERLAY_STATES:
        errors.append("invalid:state")
    if not isinstance(overlay.get("entries"), dict):
        errors.append("invalid:entries")
    else:
        for entry_id, entry in overlay["entries"].items():
            _validate_entry(entry_id, entry, errors)
    for key in ("evidence", "correction_history", "state_history"):
        if not isinstance(overlay.get(key), list):
            errors.append(f"invalid:{key}")
    if isinstance(overlay.get("evidence"), list):
        for index, evidence in enumerate(overlay["evidence"]):
            if not isinstance(evidence, dict):
                errors.append(f"invalid:evidence[{index}]")
                continue
            for key in ("evidence_id", "kind", "observed_at", "source", "content"):
                if key not in evidence:
                    errors.append(f"missing:evidence[{index}].{key}")
    retraction = overlay.get("retraction")
    if overlay.get("state") == "retracted" and not isinstance(retraction, dict):
        errors.append("missing:retraction")
    if retraction is not None and not isinstance(retraction, dict):
        errors.append("invalid:retraction")
    if errors:
        raise OverlayValidationError(errors)


def _validate_entry(entry_id: Any, entry: Any, errors: list[str]) -> None:
    label = f"entries[{entry_id!r}]"
    if not isinstance(entry_id, str) or not entry_id:
        errors.append(f"invalid:{label}.id")
    if not isinstance(entry, dict):
        errors.append(f"invalid:{label}")
        return
    for key in ("entry_id", "surface", "meaning_hypotheses", "state", "evidence_refs", "revision"):
        if key not in entry:
            errors.append(f"missing:{label}.{key}")
    if entry.get("entry_id") != entry_id:
        errors.append(f"mismatch:{label}.entry_id")
    if not isinstance(entry.get("surface"), str) or not entry.get("surface", ""):
        errors.append(f"invalid:{label}.surface")
    if not isinstance(entry.get("meaning_hypotheses"), list):
        errors.append(f"invalid:{label}.meaning_hypotheses")
    if entry.get("state") not in ENTRY_STATES:
        errors.append(f"invalid:{label}.state")
    if not isinstance(entry.get("evidence_refs"), list) or not all(isinstance(ref, str) for ref in entry.get("evidence_refs", [])):
        errors.append(f"invalid:{label}.evidence_refs")
    if not isinstance(entry.get("revision"), int) or isinstance(entry.get("revision"), bool) or entry.get("revision", 0) < 1:
        errors.append(f"invalid:{label}.revision")


class LanguageOverlayStore:
    """UTF-8 JSON store with atomic replacement and append-only audit histories."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def path_for(self, overlay_id: str) -> Path:
        if not isinstance(overlay_id, str) or not overlay_id.strip():
            raise OverlayValidationError(["invalid:overlay_id"])
        filename = unicodedata.normalize("NFC", overlay_id)
        if filename in {".", ".."} or Path(filename).name != filename or any(c in filename for c in ("/", "\\", "\x00")):
            raise OverlayValidationError(["unsafe:overlay_id"])
        return self.root / f"{filename}.json"

    def create(
        self,
        overlay_id: str,
        *,
        session_id: str,
        source_language: str = "und",
        script_hypotheses: list[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        overlay = new_overlay(
            overlay_id,
            session_id=session_id,
            source_language=source_language,
            script_hypotheses=script_hypotheses,
            metadata=metadata,
        )
        path = self.path_for(overlay_id)
        with self._lock:
            if path.exists():
                raise OverlayConflictError(f"overlay already exists: {overlay_id}")
            self._write_atomic(path, overlay)
        return copy.deepcopy(overlay)

    def load(self, overlay_id: str) -> dict[str, Any]:
        path = self.path_for(overlay_id)
        with self._lock:
            if not path.exists():
                raise OverlayNotFoundError(f"overlay not found: {overlay_id}")
            try:
                overlay = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OverlayStoreError(f"cannot read overlay {overlay_id}: {exc}") from exc
            if not isinstance(overlay, dict):
                raise OverlayValidationError(["invalid:root"])
            validate_overlay(overlay)
            return overlay

    def save(self, overlay: Mapping[str, Any], *, expected_version: int | None = None) -> dict[str, Any]:
        candidate = copy.deepcopy(dict(overlay))
        validate_overlay(candidate)
        path = self.path_for(candidate["overlay_id"])
        with self._lock:
            current = self.load(candidate["overlay_id"]) if path.exists() else None
            current_version = current["version"] if current else -1
            if expected_version is not None and current_version != expected_version:
                raise OverlayConflictError(f"version conflict: expected {expected_version}, found {current_version}")
            if current is not None and candidate["version"] != current_version:
                raise OverlayConflictError("save requires the currently persisted version")
            candidate["version"] = current_version + 1
            candidate["updated_at"] = utc_now()
            validate_overlay(candidate)
            self._write_atomic(path, candidate)
            return copy.deepcopy(candidate)

    def update(
        self,
        overlay_id: str,
        mutator: Callable[[dict[str, Any]], None],
        *,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            overlay = self.load(overlay_id)
            if expected_version is not None and overlay["version"] != expected_version:
                raise OverlayConflictError(f"version conflict: expected {expected_version}, found {overlay['version']}")
            mutator(overlay)
            return self.save(overlay, expected_version=overlay["version"])

    def add_evidence(
        self,
        overlay_id: str,
        *,
        kind: str,
        source: Mapping[str, Any] | str,
        content: Any,
        entry_id: str | None = None,
        evidence_id: str | None = None,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        evidence_id = evidence_id or f"ev-{uuid.uuid4().hex}"

        def mutate(overlay: dict[str, Any]) -> None:
            if any(row.get("evidence_id") == evidence_id for row in overlay["evidence"]):
                raise OverlayConflictError(f"duplicate evidence: {evidence_id}")
            if entry_id is not None and entry_id not in overlay["entries"]:
                raise OverlayValidationError([f"unknown:entry_id:{entry_id}"])
            row = {
                "evidence_id": evidence_id,
                "kind": kind,
                "observed_at": utc_now(),
                "source": copy.deepcopy(source),
                "content": copy.deepcopy(content),
                "entry_id": entry_id,
                "confidence": confidence,
            }
            overlay["evidence"].append(row)
            if entry_id is not None:
                overlay["entries"][entry_id]["evidence_refs"].append(evidence_id)

        return self.update(overlay_id, mutate)

    def upsert_entry(
        self,
        overlay_id: str,
        *,
        entry_id: str,
        surface: str,
        meaning_hypotheses: list[Mapping[str, Any]],
        state: str = "candidate",
        evidence_refs: list[str] | None = None,
        features: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        def mutate(overlay: dict[str, Any]) -> None:
            if state not in ENTRY_STATES:
                raise OverlayValidationError(["invalid:entry.state"])
            known_evidence = {row["evidence_id"] for row in overlay["evidence"]}
            refs = list(evidence_refs or [])
            missing = sorted(set(refs) - known_evidence)
            if missing:
                raise OverlayValidationError([f"unknown:evidence_ref:{ref}" for ref in missing])
            previous = overlay["entries"].get(entry_id)
            overlay["entries"][entry_id] = {
                "entry_id": entry_id,
                "surface": surface,
                "meaning_hypotheses": copy.deepcopy(meaning_hypotheses),
                "state": state,
                "evidence_refs": refs,
                "features": dict(features or {}),
                "revision": previous["revision"] + 1 if previous else 1,
                "created_at": previous.get("created_at", utc_now()) if previous else utc_now(),
                "updated_at": utc_now(),
            }

        return self.update(overlay_id, mutate)

    def correct_entry(
        self,
        overlay_id: str,
        entry_id: str,
        *,
        replacement: Mapping[str, Any],
        reason: str,
        evidence_refs: list[str] | None = None,
        actor: str = "teacher",
    ) -> dict[str, Any]:
        def mutate(overlay: dict[str, Any]) -> None:
            if entry_id not in overlay["entries"]:
                raise OverlayValidationError([f"unknown:entry_id:{entry_id}"])
            before = copy.deepcopy(overlay["entries"][entry_id])
            after = copy.deepcopy(before)
            allowed = {"surface", "meaning_hypotheses", "state", "evidence_refs", "features"}
            unknown = set(replacement) - allowed
            if unknown:
                raise OverlayValidationError([f"unsupported:replacement.{key}" for key in sorted(unknown)])
            after.update(copy.deepcopy(dict(replacement)))
            after["entry_id"] = entry_id
            after["revision"] = before["revision"] + 1
            after["updated_at"] = utc_now()
            refs = list(evidence_refs or [])
            known_evidence = {row["evidence_id"] for row in overlay["evidence"]}
            missing = sorted(set(refs + after.get("evidence_refs", [])) - known_evidence)
            if missing:
                raise OverlayValidationError([f"unknown:evidence_ref:{ref}" for ref in missing])
            after["evidence_refs"] = list(dict.fromkeys(after.get("evidence_refs", []) + refs))
            entry_errors: list[str] = []
            _validate_entry(entry_id, after, entry_errors)
            if entry_errors:
                raise OverlayValidationError(entry_errors)
            overlay["entries"][entry_id] = after
            overlay["correction_history"].append(
                {
                    "correction_id": f"corr-{uuid.uuid4().hex}",
                    "entry_id": entry_id,
                    "at": utc_now(),
                    "actor": actor,
                    "reason": reason,
                    "evidence_refs": refs,
                    "before": before,
                    "after": copy.deepcopy(after),
                }
            )

        return self.update(overlay_id, mutate)

    def transition(self, overlay_id: str, state: str, *, reason: str, actor: str = "system") -> dict[str, Any]:
        if state not in OVERLAY_STATES:
            raise OverlayValidationError(["invalid:state"])

        def mutate(overlay: dict[str, Any]) -> None:
            if overlay["state"] == "retracted":
                raise OverlayConflictError("a retracted overlay cannot transition")
            previous = overlay["state"]
            overlay["state"] = state
            overlay["state_history"].append(
                {"from": previous, "to": state, "at": utc_now(), "reason": reason, "actor": actor}
            )

        return self.update(overlay_id, mutate)

    def retract(
        self,
        overlay_id: str,
        *,
        reason: str,
        actor: str,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        def mutate(overlay: dict[str, Any]) -> None:
            if overlay["state"] == "retracted":
                raise OverlayConflictError("overlay is already retracted")
            refs = list(evidence_refs or [])
            known_evidence = {row["evidence_id"] for row in overlay["evidence"]}
            missing = sorted(set(refs) - known_evidence)
            if missing:
                raise OverlayValidationError([f"unknown:evidence_ref:{ref}" for ref in missing])
            previous = overlay["state"]
            overlay["state"] = "retracted"
            overlay["retraction"] = {
                "at": utc_now(),
                "actor": actor,
                "reason": reason,
                "evidence_refs": refs,
            }
            overlay["state_history"].append(
                {"from": previous, "to": "retracted", "at": utc_now(), "reason": reason, "actor": actor}
            )

        return self.update(overlay_id, mutate)

    @staticmethod
    def _write_atomic(path: Path, overlay: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(overlay, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
            if os.name != "nt":
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except BaseException:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise


SessionLanguageOverlayStore = LanguageOverlayStore
