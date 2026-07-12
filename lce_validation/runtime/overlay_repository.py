from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Protocol


class LanguageOverlayRepository(Protocol):
    def create(self, overlay_id: str, *, session_id: str, source_language: str = "und", script_hypotheses: list[str] | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def load(self, overlay_id: str) -> dict[str, Any]: ...
    def save(self, overlay: dict[str, Any], *, expected_version: int | None = None) -> dict[str, Any]: ...
    def update(self, overlay_id: str, mutator: Callable[[dict[str, Any]], None], *, expected_version: int | None = None) -> dict[str, Any]: ...


def create_overlay_repository() -> LanguageOverlayRepository:
    backend = os.environ.get("LCE_OVERLAY_BACKEND", "json").strip().lower()
    if backend == "json":
        from .language_overlay_store import LanguageOverlayStore

        return LanguageOverlayStore(Path(os.environ.get("LCE_LANGUAGE_OVERLAY_ROOT", ".lce-data/language-overlays")))
    if backend == "mysql":
        from .mysql_overlay_repository import MySQLLanguageOverlayRepository, connect_from_environment

        return MySQLLanguageOverlayRepository(connect_from_environment)
    raise ValueError(f"unsupported LCE_OVERLAY_BACKEND: {backend}")
