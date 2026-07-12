from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Protocol
from uuid import UUID


CANONICAL_SCHEMA_VERSION = 1


class MigrationError(RuntimeError):
    pass


class MigrationConflictError(MigrationError):
    pass


class MigrationVerificationError(MigrationError):
    pass


class MigrationTarget(Protocol):
    """Minimal adapter contract implemented by the MySQL repository."""

    def import_record(self, record: Mapping[str, Any], *, idempotency_key: str) -> Any: ...

    def export_record(self, logical_id: str, revision: int | str) -> Mapping[str, Any]: ...

    def iter_export_records(self, *, after_key: str | None = None) -> Iterable[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class MigrationCheckpoint:
    source_fingerprint: str
    last_key: str | None = None
    processed: int = 0
    imported: int = 0
    verified: int = 0
    failed: int = 0
    completed: bool = False
    updated_at: str = ""


@dataclass(frozen=True)
class MigrationResult:
    dry_run: bool
    processed: int
    imported: int
    verified: int
    skipped: int
    failed: int
    checkpoint: MigrationCheckpoint
    elapsed_seconds: float = 0.0
    records_per_second: float = 0.0
    batches: int = 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_json_value(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value).lower()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return value.hex()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_bytes(record: Mapping[str, Any]) -> bytes:
    """Return stable UTF-8 bytes without altering original string content."""
    envelope = {"canonical_schema_version": CANONICAL_SCHEMA_VERSION, "record": _json_value(record)}
    return json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_hash(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(record)).hexdigest()


def record_key(record: Mapping[str, Any], *, tenant_id: str | None = None) -> str:
    tenant = tenant_id or record.get("tenant_id")
    logical_id = record.get("knowledge_id", record.get("logical_id"))
    revision = record.get("revision", record.get("revision_no", record.get("version")))
    if logical_id is None or revision is None:
        raise MigrationError("record requires knowledge_id/logical_id and revision/revision_no/version")
    base = f"{logical_id}:{revision}"
    return f"{tenant}:{base}" if tenant is not None else base


def _tenant_record(record: Mapping[str, Any], tenant_id: str | None) -> dict[str, Any]:
    result = dict(record)
    embedded = result.get("tenant_id")
    if tenant_id is None and embedded is None:
        return result
    effective = str(tenant_id if tenant_id is not None else embedded)
    if embedded is not None and str(embedded) != effective:
        raise MigrationConflictError("record tenant does not match migration tenant")
    result["tenant_id"] = effective
    return result


def read_json_records(path: str | Path) -> Iterator[dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() == ".jsonl":
        with source.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise MigrationError(f"{source}:{line_no}: record must be an object")
                yield value
        return
    value = json.loads(source.read_text(encoding="utf-8"))
    records = value.get("records") if isinstance(value, dict) and "records" in value else value
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        raise MigrationError(f"{source}: expected object, array, or records array")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise MigrationError(f"{source}: record {index} must be an object")
        yield record


def source_fingerprint(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_checkpoint(path: str | Path, *, expected_source: str) -> MigrationCheckpoint:
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        return MigrationCheckpoint(source_fingerprint=expected_source, updated_at=_utc_now())
    data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint = MigrationCheckpoint(**data)
    if checkpoint.source_fingerprint != expected_source:
        raise MigrationConflictError("checkpoint belongs to a different source snapshot")
    return checkpoint


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def save_checkpoint(path: str | Path, checkpoint: MigrationCheckpoint) -> None:
    _atomic_json(Path(path), asdict(checkpoint))


def _target_import(target: Any, record: Mapping[str, Any], key: str) -> Any:
    method = getattr(target, "import_record", None) or getattr(target, "import_revision", None)
    if method is None:
        raise MigrationError("target must provide import_record or import_revision")
    return method(record, idempotency_key=key)


def _target_export(target: Any, record: Mapping[str, Any]) -> Mapping[str, Any]:
    logical_id = record.get("knowledge_id", record.get("logical_id"))
    revision = record.get("revision", record.get("revision_no", record.get("version")))
    method = getattr(target, "export_record", None) or getattr(target, "get_revision", None)
    if method is None:
        raise MigrationError("target must provide export_record or get_revision")
    tenant_id = record.get("tenant_id")
    try:
        exported = method(str(logical_id), revision, tenant_id=tenant_id)
    except TypeError:
        exported = method(str(logical_id), revision)
    if not isinstance(exported, Mapping):
        raise MigrationVerificationError("target export is not an object")
    return exported


def verify_record(source: Mapping[str, Any], target: Mapping[str, Any]) -> None:
    source_digest = canonical_hash(source)
    target_digest = canonical_hash(target)
    if source_digest != target_digest:
        raise MigrationVerificationError(f"canonical mismatch for {record_key(source)}: {source_digest} != {target_digest}")


def backfill_json_to_mysql(
    source_path: str | Path,
    target: MigrationTarget,
    *,
    checkpoint_path: str | Path,
    dry_run: bool = False,
    verify_after_write: bool = True,
    validator: Callable[[Mapping[str, Any]], None] | None = None,
    tenant_id: str | None = None,
    batch_size: int = 100,
    clock: Callable[[], float] = time.perf_counter,
) -> MigrationResult:
    """Idempotent one-way migration. It never writes back to the JSON source."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    started = clock()
    raw_fingerprint = source_fingerprint(source_path)
    fingerprint = hashlib.sha256(f"{raw_fingerprint}\0{tenant_id or ''}".encode()).hexdigest() if tenant_id else raw_fingerprint
    checkpoint = load_checkpoint(checkpoint_path, expected_source=fingerprint)
    if checkpoint.completed:
        return MigrationResult(dry_run, 0, 0, 0, 0, 0, checkpoint)

    records = [_tenant_record(record, tenant_id) for record in read_json_records(source_path)]
    records.sort(key=lambda record: record_key(record, tenant_id=tenant_id))
    processed = imported = verified = skipped = failed = 0
    batches = 0
    for record in records:
        key = record_key(record, tenant_id=tenant_id)
        if checkpoint.last_key is not None and key <= checkpoint.last_key:
            skipped += 1
            continue
        try:
            if validator is not None:
                validator(record)
            canonical_bytes(record)
            processed += 1
            if not dry_run:
                _target_import(target, record, key)
                imported += 1
                if verify_after_write:
                    verify_record(record, _target_export(target, record))
                    verified += 1
                checkpoint = MigrationCheckpoint(fingerprint, key, checkpoint.processed + 1, checkpoint.imported + 1,
                    checkpoint.verified + (1 if verify_after_write else 0), checkpoint.failed, False, _utc_now())
                if imported % batch_size == 0:
                    save_checkpoint(checkpoint_path, checkpoint)
                    batches += 1
        except Exception:
            failed += 1
            if not dry_run:
                checkpoint = MigrationCheckpoint(
                    fingerprint, checkpoint.last_key, checkpoint.processed, checkpoint.imported,
                    checkpoint.verified, checkpoint.failed + 1, False, _utc_now(),
                )
                save_checkpoint(checkpoint_path, checkpoint)
            raise

    if not dry_run:
        checkpoint = MigrationCheckpoint(
            fingerprint, checkpoint.last_key, checkpoint.processed, checkpoint.imported,
            checkpoint.verified, checkpoint.failed, True, _utc_now(),
        )
        save_checkpoint(checkpoint_path, checkpoint)
        if imported % batch_size:
            batches += 1
    elapsed = max(0.0, clock() - started)
    rate = processed / elapsed if elapsed > 0 else 0.0
    return MigrationResult(dry_run, processed, imported, verified, skipped, failed, checkpoint, elapsed, rate, batches)


def dual_read_verify(source_path: str | Path, target: MigrationTarget, *, tenant_id: str | None = None) -> dict[str, Any]:
    """Compare both stores without fallback or mutation."""
    mismatches: list[dict[str, str]] = []
    checked = 0
    for raw in read_json_records(source_path):
        source = _tenant_record(raw, tenant_id)
        checked += 1
        try:
            target_record = _target_export(target, source)
            verify_record(source, target_record)
        except Exception as exc:
            mismatches.append({"key": record_key(source, tenant_id=tenant_id), "error": str(exc)})
    return {"checked": checked, "matched": checked - len(mismatches), "mismatches": mismatches, "ok": not mismatches}


def export_rollback_snapshot(target: MigrationTarget, destination: str | Path, *, after_key: str | None = None,
                             tenant_id: str | None = None, batch_size: int = 100) -> dict[str, Any]:
    """Export a new recovery JSONL snapshot; existing JSON is never overwritten."""
    destination_path = Path(destination)
    if destination_path.exists():
        raise MigrationConflictError(f"rollback export already exists: {destination_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination_path.name}.", suffix=".tmp", dir=destination_path.parent)
    count = 0
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as handle:
            try:
                records = target.iter_export_records(after_key=after_key, tenant_id=tenant_id, batch_size=batch_size)
            except TypeError:
                records = target.iter_export_records(after_key=after_key)
            for record in records:
                if not isinstance(record, Mapping):
                    raise MigrationError("rollback export record must be an object")
                record = _tenant_record(record, tenant_id)
                line = json.dumps(_json_value(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
                handle.write(line)
                digest.update(line)
                count += 1
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination_path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    manifest = {"path": str(destination_path), "record_count": count, "sha256": digest.hexdigest(),
                "created_at": _utc_now(), "after_key": after_key, "tenant_id": tenant_id,
                "batch_size": batch_size, "canonical_schema_version": CANONICAL_SCHEMA_VERSION}
    _atomic_json(destination_path.with_suffix(destination_path.suffix + ".manifest.json"), manifest)
    return manifest


def verify_rollback_snapshot(destination: str | Path, manifest_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(destination)
    manifest_file = Path(manifest_path) if manifest_path else path.with_suffix(path.suffix + ".manifest.json")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    count = sum(1 for line in path.read_bytes().splitlines() if line.strip())
    ok = digest == manifest.get("sha256") and count == manifest.get("record_count")
    return {"ok": ok, "sha256": digest, "record_count": count, "manifest": manifest}
