"""Data-only Model Pack contracts for the first Open Core shadow slice."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PACK_SCHEMA_VERSION = "lce-pack/v1"
PROFILE_SCHEMA_VERSION = "lce-profile/v1"
CORE_ENGINE_COMPATIBILITY = "lce-core/v1"


class PackValidationError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PackValidationError("NON_CANONICAL_PACK_JSON") from exc


def content_hash(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(dict(payload)).encode("utf-8")).hexdigest()


def load_pack(path: str | Path) -> dict[str, Any]:
    try:
        pack = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackValidationError("UNREADABLE_PACK") from exc
    validate_pack(pack)
    return pack


def validate_pack(pack: Mapping[str, Any]) -> None:
    required = {"schema_version", "pack_id", "pack_version", "pack_type", "engine_compatibility", "content_hash", "capabilities", "payload"}
    if not isinstance(pack, Mapping) or required - set(pack):
        raise PackValidationError("INVALID_PACK_ENVELOPE")
    if pack["schema_version"] != PACK_SCHEMA_VERSION or pack["engine_compatibility"] != CORE_ENGINE_COMPATIBILITY:
        raise PackValidationError("PACK_VERSION_INCOMPATIBLE")
    if not all(isinstance(pack[key], str) and pack[key] for key in ("pack_id", "pack_version", "pack_type", "content_hash")):
        raise PackValidationError("INVALID_PACK_IDENTITY")
    if not isinstance(pack["capabilities"], list) or not all(isinstance(item, str) for item in pack["capabilities"]):
        raise PackValidationError("INVALID_PACK_CAPABILITIES")
    if not isinstance(pack["payload"], Mapping) or pack["content_hash"] != content_hash(pack["payload"]):
        raise PackValidationError("PACK_CONTENT_HASH_MISMATCH")
    if pack["pack_type"] == "LanguagePack":
        _validate_language_payload(pack["payload"])


def lock_profile(profile: Mapping[str, Any], packs: list[Mapping[str, Any]]) -> dict[str, Any]:
    required = {"schema_version", "profile_id", "profile_version", "engine_compatibility", "pack_refs", "capabilities"}
    if not isinstance(profile, Mapping) or required - set(profile):
        raise PackValidationError("INVALID_PROFILE")
    if profile["schema_version"] != PROFILE_SCHEMA_VERSION or profile["engine_compatibility"] != CORE_ENGINE_COMPATIBILITY:
        raise PackValidationError("PROFILE_VERSION_INCOMPATIBLE")
    if not isinstance(profile["pack_refs"], list) or not isinstance(profile["capabilities"], list):
        raise PackValidationError("INVALID_PROFILE_FIELDS")
    indexed: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for pack in packs:
        validate_pack(pack)
        indexed[(str(pack["pack_id"]), str(pack["pack_version"]), str(pack["content_hash"]))] = pack
    refs = []
    for ref in profile["pack_refs"]:
        if not isinstance(ref, Mapping):
            raise PackValidationError("INVALID_PROFILE_PACK_REF")
        key = (str(ref.get("pack_id")), str(ref.get("pack_version")), str(ref.get("content_hash")))
        if key not in indexed:
            raise PackValidationError("PROFILE_PACK_NOT_LOCKED")
        refs.append({"pack_id": key[0], "pack_version": key[1], "content_hash": key[2]})
    lock = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profile_id": profile["profile_id"],
        "profile_version": profile["profile_version"],
        "engine_compatibility": profile["engine_compatibility"],
        "capabilities": sorted(profile["capabilities"]),
        "pack_refs": sorted(refs, key=lambda row: (row["pack_id"], row["pack_version"], row["content_hash"])),
    }
    lock["profile_lock_hash"] = "sha256:" + hashlib.sha256(canonical_json(lock).encode("utf-8")).hexdigest()
    return lock


def recognize_language_pack(text: str, pack: Mapping[str, Any]) -> dict[str, Any]:
    """Interpret a data-only LanguagePack without allowing it to mutate state."""
    validate_pack(pack)
    if pack["pack_type"] != "LanguagePack":
        raise PackValidationError("NOT_LANGUAGE_PACK")
    lowered = text.casefold()
    cues: list[str] = []
    legacy_rule_ids: list[str] = []
    for rule in pack["payload"]["rules"]:
        if any(pattern.casefold() in lowered for pattern in rule["patterns"]):
            if rule["cue"] not in cues:
                cues.append(rule["cue"])
            if rule["legacy_rule_id"] not in legacy_rule_ids:
                legacy_rule_ids.append(rule["legacy_rule_id"])
    return {"pack_id": pack["pack_id"], "cues": cues, "legacy_rule_ids": legacy_rule_ids}


def _validate_language_payload(payload: Mapping[str, Any]) -> None:
    if set(payload) != {"rules"} or not isinstance(payload["rules"], list) or not payload["rules"]:
        raise PackValidationError("INVALID_LANGUAGE_PAYLOAD")
    seen: set[str] = set()
    for rule in payload["rules"]:
        if not isinstance(rule, Mapping) or {"legacy_rule_id", "cue", "patterns"} - set(rule):
            raise PackValidationError("INVALID_LANGUAGE_RULE")
        if not isinstance(rule["legacy_rule_id"], str) or rule["legacy_rule_id"] in seen:
            raise PackValidationError("DUPLICATE_LANGUAGE_RULE")
        seen.add(rule["legacy_rule_id"])
        if not isinstance(rule["cue"], str) or not isinstance(rule["patterns"], list) or not rule["patterns"] or not all(isinstance(item, str) and item for item in rule["patterns"]):
            raise PackValidationError("INVALID_LANGUAGE_RULE")
