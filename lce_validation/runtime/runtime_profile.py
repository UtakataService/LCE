"""Runtime selection of Profile-pinned data-only Packs."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Mapping

from .model_pack import PackValidationError, load_pack, lock_profile


REFERENCE_FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures"
REFERENCE_PROFILE_PATH = REFERENCE_FIXTURE_ROOT / "reference_profile_frame_v1.json"


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    lock: dict[str, Any]
    frame_pack: dict[str, Any]
    semantic_cube_pack: dict[str, Any]
    signal_packs: tuple[dict[str, Any], ...] = ()

    def trace_identity(self) -> dict[str, Any]:
        return {
            "profile_id": self.lock["profile_id"],
            "profile_version": self.lock["profile_version"],
            "profile_lock_hash": self.lock["profile_lock_hash"],
            "pack_refs": list(self.lock["pack_refs"]),
        }


def load_runtime_profile(profile_path: str | Path, pack_root: str | Path | None = None) -> RuntimeProfile:
    profile_target = Path(profile_path)
    root = Path(pack_root) if pack_root is not None else profile_target.parent
    try:
        profile = json.loads(profile_target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackValidationError("UNREADABLE_PROFILE") from exc
    packs = _load_profile_packs(profile, root)
    lock = lock_profile(profile, packs)
    frame_packs = [pack for pack in packs if pack["pack_type"] == "LanguagePack" and "frame.core.v1" in pack["capabilities"]]
    semantic_packs = [pack for pack in packs if pack["pack_type"] == "SemanticCube"]
    signal_packs = [pack for pack in packs if pack["pack_type"] == "LanguagePack" and any(capability.startswith("signal.") for capability in pack["capabilities"])]
    if len(frame_packs) != 1 or len(semantic_packs) != 1:
        raise PackValidationError("RUNTIME_PROFILE_REQUIRED_PACK_MISSING")
    return RuntimeProfile(lock=lock, frame_pack=frame_packs[0], semantic_cube_pack=semantic_packs[0], signal_packs=tuple(signal_packs))


@lru_cache(maxsize=1)
def reference_runtime_profile() -> RuntimeProfile:
    return load_runtime_profile(REFERENCE_PROFILE_PATH, REFERENCE_FIXTURE_ROOT)


def _load_profile_packs(profile: Mapping[str, Any], root: Path) -> list[dict[str, Any]]:
    refs = profile.get("pack_refs")
    if not isinstance(refs, list):
        raise PackValidationError("INVALID_PROFILE_PACK_REFS")
    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PackValidationError("UNREADABLE_PACK") from exc
        if raw.get("schema_version") == "lce-pack/v1":
            pack = load_pack(path)
            indexed[(pack["pack_id"], pack["pack_version"], pack["content_hash"])] = pack
    selected = []
    for ref in refs:
        key = (str(ref.get("pack_id")), str(ref.get("pack_version")), str(ref.get("content_hash"))) if isinstance(ref, Mapping) else None
        if key not in indexed:
            raise PackValidationError("PROFILE_PACK_NOT_LOCKED")
        selected.append(indexed[key])
    return selected
