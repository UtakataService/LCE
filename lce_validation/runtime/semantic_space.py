"""Language-independent semantic units projected onto stable Cube coordinates."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from .model_pack import CORE_ENGINE_COMPATIBILITY, PACK_SCHEMA_VERSION


SEMANTIC_CUBE_PACK_TYPE = "SemanticCube"
SEMANTIC_CUBE_PATH = Path(__file__).parents[1] / "fixtures" / "reference_semantic_cube_v1.json"
REQUIRED_COORDINATE_AXES = ("domain", "speech_act", "interaction", "epistemic", "affect", "reference")


class SemanticCubeValidationError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def semantic_cube_content_hash(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(dict(payload)).encode("utf-8")).hexdigest()


def load_semantic_cube(path: str | Path = SEMANTIC_CUBE_PATH) -> dict[str, Any]:
    try:
        cube = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SemanticCubeValidationError("UNREADABLE_SEMANTIC_CUBE") from exc
    validate_semantic_cube(cube)
    return cube


def validate_semantic_cube(cube: Mapping[str, Any]) -> None:
    required = {"schema_version", "pack_id", "pack_version", "pack_type", "engine_compatibility", "content_hash", "capabilities", "payload"}
    if not isinstance(cube, Mapping) or required - set(cube):
        raise SemanticCubeValidationError("INVALID_SEMANTIC_CUBE_ENVELOPE")
    if cube["schema_version"] != PACK_SCHEMA_VERSION or cube["engine_compatibility"] != CORE_ENGINE_COMPATIBILITY or cube["pack_type"] != SEMANTIC_CUBE_PACK_TYPE:
        raise SemanticCubeValidationError("SEMANTIC_CUBE_VERSION_INCOMPATIBLE")
    if not all(isinstance(cube[key], str) and cube[key] for key in ("pack_id", "pack_version", "content_hash")):
        raise SemanticCubeValidationError("INVALID_SEMANTIC_CUBE_IDENTITY")
    payload = cube["payload"]
    if not isinstance(payload, Mapping) or cube["content_hash"] != semantic_cube_content_hash(payload):
        raise SemanticCubeValidationError("SEMANTIC_CUBE_CONTENT_HASH_MISMATCH")
    if payload.get("axes") != list(REQUIRED_COORDINATE_AXES) or not isinstance(payload.get("units"), list):
        raise SemanticCubeValidationError("INVALID_SEMANTIC_CUBE_PAYLOAD")
    seen_ids: set[str] = set()
    seen_labels: set[str] = set()
    for unit in payload["units"]:
        if not isinstance(unit, Mapping) or {"semantic_id", "coordinates", "labels"} - set(unit):
            raise SemanticCubeValidationError("INVALID_SEMANTIC_UNIT")
        semantic_id = unit["semantic_id"]
        coordinates = unit["coordinates"]
        labels = unit["labels"]
        if not isinstance(semantic_id, str) or not semantic_id or semantic_id in seen_ids:
            raise SemanticCubeValidationError("DUPLICATE_SEMANTIC_ID")
        if not isinstance(coordinates, Mapping) or set(coordinates) != set(REQUIRED_COORDINATE_AXES):
            raise SemanticCubeValidationError("INVALID_SEMANTIC_COORDINATES")
        if not all(isinstance(value, str) and value for value in coordinates.values()):
            raise SemanticCubeValidationError("INVALID_SEMANTIC_COORDINATES")
        if not isinstance(labels, list) or not labels or not all(isinstance(label, str) and label for label in labels):
            raise SemanticCubeValidationError("INVALID_SEMANTIC_LABELS")
        if seen_labels & set(labels):
            raise SemanticCubeValidationError("DUPLICATE_SEMANTIC_LABEL")
        seen_ids.add(semantic_id)
        seen_labels.update(labels)


def resolve_semantic_units(labels: list[str] | tuple[str, ...], rule_ids: list[str] | tuple[str, ...] = (), *, semantic_cube: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Resolve language-pack labels to canonical meaning points without scoring or mutation."""
    if not isinstance(labels, (list, tuple)) or not all(isinstance(label, str) for label in labels):
        raise SemanticCubeValidationError("INVALID_SEMANTIC_LABEL_INPUT")
    cube = dict(semantic_cube) if semantic_cube is not None else _reference_semantic_cube()
    validate_semantic_cube(cube)
    rules_by_label = _rules_by_label(cube)
    rule_lookup = {label: rule_id for label, rule_id in zip(labels, rule_ids)}
    units: list[dict[str, Any]] = []
    unmapped: list[str] = []
    for label in labels:
        unit = rules_by_label.get(label)
        if unit is None:
            unmapped.append(label)
            continue
        row = {
            "semantic_id": unit["semantic_id"],
            "coordinates": dict(unit["coordinates"]),
            "source_label": label,
            "source_rule_id": rule_lookup.get(label, ""),
        }
        if not any(existing["semantic_id"] == row["semantic_id"] for existing in units):
            units.append(row)
    return {
        "semantic_cube_id": cube["pack_id"],
        "semantic_cube_version": cube["pack_version"],
        "semantic_ids": [unit["semantic_id"] for unit in units],
        "units": units,
        "unmapped_labels": unmapped,
    }


@lru_cache(maxsize=1)
def _reference_semantic_cube() -> dict[str, Any]:
    return load_semantic_cube()


def _rules_by_label(cube: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        label: unit
        for unit in cube["payload"]["units"]
        for label in unit["labels"]
    }
