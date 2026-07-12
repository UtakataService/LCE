"""Local JSON repository and conformance helpers for data-only Model Packs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .model_pack import PACK_SCHEMA_VERSION, PackValidationError, canonical_json, load_pack, lock_profile, recognize_language_pack
from .utterance_frame import frame_utterance, frame_utterance_legacy


class JsonPackRepository:
    """Read-only, deterministic local Pack repository for experimental SDK use."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def list_packs(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            raise PackValidationError("PACK_REPOSITORY_UNAVAILABLE")
        packs = []
        for path in sorted(self.root.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PackValidationError("UNREADABLE_PACK") from exc
            if raw.get("schema_version") == PACK_SCHEMA_VERSION:
                packs.append(load_pack(path))
        keys = [(pack["pack_id"], pack["pack_version"], pack["content_hash"]) for pack in packs]
        if len(keys) != len(set(keys)):
            raise PackValidationError("DUPLICATE_PACK_IDENTITY")
        return packs

    def resolve(self, pack_id: str, pack_version: str, content_hash: str) -> dict[str, Any]:
        for pack in self.list_packs():
            if (pack["pack_id"], pack["pack_version"], pack["content_hash"]) == (pack_id, pack_version, content_hash):
                return pack
        raise PackValidationError("PACK_NOT_FOUND")


def load_profile(path: str | Path) -> dict[str, Any]:
    try:
        profile = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackValidationError("UNREADABLE_PROFILE") from exc
    return profile


def lock_profile_from_repository(profile: Mapping[str, Any], repository: JsonPackRepository) -> dict[str, Any]:
    refs = profile.get("pack_refs")
    if not isinstance(refs, list):
        raise PackValidationError("INVALID_PROFILE_PACK_REFS")
    packs = [repository.resolve(str(ref.get("pack_id")), str(ref.get("pack_version")), str(ref.get("content_hash"))) for ref in refs if isinstance(ref, Mapping)]
    if len(packs) != len(refs):
        raise PackValidationError("INVALID_PROFILE_PACK_REFS")
    return lock_profile(profile, packs)


def run_language_pack_conformance(pack: Mapping[str, Any], fixtures_path: str | Path) -> dict[str, Any]:
    rows = _read_jsonl(fixtures_path)
    results: list[dict[str, Any]] = []
    for row in rows:
        required = {"case_id", "text", "expected_cues"}
        if not isinstance(row, Mapping) or required - set(row) or not isinstance(row["expected_cues"], list):
            raise PackValidationError("INVALID_CONFORMANCE_FIXTURE")
        actual = recognize_language_pack(str(row["text"]), pack)
        results.append({
            "case_id": row["case_id"],
            "passed": actual["cues"] == row["expected_cues"],
            "expected_cues": row["expected_cues"],
            "actual_cues": actual["cues"],
        })
    return {"fixture_count": len(results), "passed": sum(item["passed"] for item in results), "failed": sum(not item["passed"] for item in results), "results": results}


def build_frame_difference_ledger(fixtures_path: str | Path) -> list[dict[str, Any]]:
    """Compare active Pack recognition with frozen legacy recognition without raw text."""
    rows = _read_jsonl(fixtures_path)
    ledger: list[dict[str, Any]] = []
    for row in rows:
        active = frame_utterance(str(row["text"]))
        legacy = frame_utterance_legacy(str(row["text"]))
        active_hash = _hash(active)
        legacy_hash = _hash(legacy)
        ledger.append({
            "case_id": row["case_id"],
            "active_hash": active_hash,
            "legacy_hash": legacy_hash,
            "equal": active == legacy,
            "difference_fields": sorted(key for key in set(active) | set(legacy) if active.get(key) != legacy.get(key)),
        })
    return ledger


def write_difference_ledger(path: str | Path, ledger: list[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(canonical_json(dict(row)) + "\n" for row in ledger), encoding="utf-8")


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    try:
        return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PackValidationError("UNREADABLE_CONFORMANCE_FIXTURE") from exc


def _hash(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(dict(value)).encode("utf-8")).hexdigest()
