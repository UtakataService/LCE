"""Experimental public facade for the LCE data-only Open Core SDK."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .runtime.model_pack_repository import (
    JsonPackRepository,
    build_frame_difference_ledger,
    load_profile,
    lock_profile_from_repository,
    run_language_pack_conformance,
)


class OpenCoreSdk:
    """Read-only Pack loading, profile locking, and conformance surface.

    This facade intentionally exposes no arbitrary plugin execution, state
    commit, or normal dialogue route replacement.
    """

    def __init__(self, pack_directory: str | Path):
        self.repository = JsonPackRepository(pack_directory)

    def lock_profile(self, profile_path: str | Path) -> dict[str, Any]:
        return lock_profile_from_repository(load_profile(profile_path), self.repository)

    def run_language_conformance(self, pack_id: str, pack_version: str, content_hash: str, fixtures_path: str | Path) -> dict[str, Any]:
        pack = self.repository.resolve(pack_id, pack_version, content_hash)
        return run_language_pack_conformance(pack, fixtures_path)

    def frame_shadow_difference_ledger(self, fixtures_path: str | Path) -> list[dict[str, Any]]:
        return build_frame_difference_ledger(fixtures_path)
