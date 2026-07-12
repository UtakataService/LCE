from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from typing import Any, Callable

from .language_overlay_store import (
    OverlayConflictError,
    OverlayNotFoundError,
    new_overlay,
    utc_now,
    validate_overlay,
)


def connect_from_environment() -> Any:
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError("MySQL backend requires the optional 'pymysql' package") from exc
    return pymysql.connect(
        host=os.environ.get("LCE_MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("LCE_MYSQL_PORT", "3306")),
        user=os.environ["LCE_MYSQL_USER"],
        password=os.environ["LCE_MYSQL_PASSWORD"],
        database=os.environ.get("LCE_MYSQL_DATABASE", "lce"),
        charset="utf8mb4",
        autocommit=False,
    )


class MySQLLanguageOverlayRepository:
    """MySQL document repository with optimistic versioning and row locks."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self.connection_factory = connection_factory

    def create(self, overlay_id: str, *, session_id: str, source_language: str = "und", script_hypotheses: list[str] | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        overlay = new_overlay(overlay_id, session_id=session_id, source_language=source_language, script_hypotheses=script_hypotheses, metadata=metadata)
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO language_overlays (overlay_id, session_id, source_language, state, version, payload_json, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    self._row(overlay),
                )
            connection.commit()
            return copy.deepcopy(overlay)
        except Exception as exc:
            connection.rollback()
            if self._is_duplicate(exc):
                raise OverlayConflictError(f"overlay already exists: {overlay_id}") from exc
            raise
        finally:
            connection.close()

    def load(self, overlay_id: str) -> dict[str, Any]:
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT payload_json FROM language_overlays WHERE overlay_id=%s", (overlay_id,))
                row = cursor.fetchone()
            if row is None:
                raise OverlayNotFoundError(f"overlay not found: {overlay_id}")
            payload = row[0] if not isinstance(row, dict) else row["payload_json"]
            overlay = json.loads(payload) if isinstance(payload, (str, bytes, bytearray)) else payload
            validate_overlay(overlay)
            return overlay
        finally:
            connection.close()

    def save(self, overlay: dict[str, Any], *, expected_version: int | None = None) -> dict[str, Any]:
        candidate = copy.deepcopy(overlay)
        validate_overlay(candidate)
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version FROM language_overlays WHERE overlay_id=%s FOR UPDATE", (candidate["overlay_id"],))
                row = cursor.fetchone()
                if row is None:
                    raise OverlayNotFoundError(f"overlay not found: {candidate['overlay_id']}")
                current = int(row[0] if not isinstance(row, dict) else row["version"])
                if expected_version is not None and current != expected_version:
                    raise OverlayConflictError(f"version conflict: expected {expected_version}, found {current}")
                if candidate["version"] != current:
                    raise OverlayConflictError("save requires the currently persisted version")
                candidate["version"] = current + 1
                candidate["updated_at"] = utc_now()
                validate_overlay(candidate)
                cursor.execute(
                    "UPDATE language_overlays SET session_id=%s, source_language=%s, state=%s, version=%s, payload_json=%s, updated_at=%s WHERE overlay_id=%s AND version=%s",
                    (candidate["session_id"], candidate["source_language"], candidate["state"], candidate["version"], self._payload(candidate), self._mysql_time(candidate["updated_at"]), candidate["overlay_id"], current),
                )
                if cursor.rowcount != 1:
                    raise OverlayConflictError("concurrent overlay update")
            connection.commit()
            return candidate
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def update(self, overlay_id: str, mutator: Callable[[dict[str, Any]], None], *, expected_version: int | None = None) -> dict[str, Any]:
        overlay = self.load(overlay_id)
        if expected_version is not None and overlay["version"] != expected_version:
            raise OverlayConflictError(f"version conflict: expected {expected_version}, found {overlay['version']}")
        mutator(overlay)
        return self.save(overlay, expected_version=overlay["version"])

    @staticmethod
    def _payload(overlay: dict[str, Any]) -> str:
        return json.dumps(overlay, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def _row(cls, overlay: dict[str, Any]) -> tuple[Any, ...]:
        return (overlay["overlay_id"], overlay["session_id"], overlay["source_language"], overlay["state"], overlay["version"], cls._payload(overlay), cls._mysql_time(overlay["created_at"]), cls._mysql_time(overlay["updated_at"]))

    @staticmethod
    def _mysql_time(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    @staticmethod
    def _is_duplicate(exc: Exception) -> bool:
        return bool(getattr(exc, "args", ())) and exc.args[0] == 1062
