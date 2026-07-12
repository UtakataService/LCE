"""Governed post-training manifests for SFT, preference, and safety stages."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class PostTrainingContractError(ValueError):
    pass


STAGES = {"sft", "preference", "safety"}
ALLOWED_SPLITS = {"train", "validation", "interaction_blind", "sealed", "quarantine"}
REQUIRED_STAGE_FIELDS = {
    "sft": {"instruction_schema_hash", "response_schema_hash"},
    "preference": {"pair_schema_hash", "rater_policy_id"},
    "safety": {"policy_pack_hash", "adjudication_policy_id"},
}


@dataclass(frozen=True, slots=True)
class PostTrainingManifest:
    manifest_id: str
    manifest_version: str
    stages: tuple[dict[str, Any], ...]
    snapshot_hash: str

    def train_stages(self) -> tuple[str, ...]:
        return tuple(stage["stage"] for stage in self.stages if stage["split"] == "train")


def load_post_training_manifest(path: str | Path) -> PostTrainingManifest:
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PostTrainingContractError("UNREADABLE_POST_TRAINING_MANIFEST") from exc
    return validate_post_training_manifest(raw)


def validate_post_training_manifest(raw: Mapping[str, Any]) -> PostTrainingManifest:
    required = {"schema_version", "manifest_id", "manifest_version", "stages"}
    if not isinstance(raw, Mapping) or raw.get("schema_version") != "lce-post-training/v1" or required - set(raw):
        raise PostTrainingContractError("INVALID_POST_TRAINING_MANIFEST_SCHEMA")
    if not isinstance(raw["manifest_id"], str) or not isinstance(raw["manifest_version"], str):
        raise PostTrainingContractError("INVALID_POST_TRAINING_MANIFEST_IDENTITY")
    stages = _validate_stages(raw["stages"])
    snapshot_hash = "sha256:" + hashlib.sha256(_canonical_json(dict(raw)).encode("utf-8")).hexdigest()
    return PostTrainingManifest(raw["manifest_id"], raw["manifest_version"], stages, snapshot_hash)


def _validate_stages(value: Any) -> tuple[dict[str, Any], ...]:
    common = {"stage_id", "stage", "split", "source_family", "license_manifest_hash", "consent_basis", "row_count", "content_snapshot_hash", "dedup_policy_id"}
    if not isinstance(value, list) or not value:
        raise PostTrainingContractError("INVALID_POST_TRAINING_STAGES")
    ids: set[str] = set()
    lineage: dict[tuple[str, str], str] = {}
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping) or common - set(item) or item.get("stage") not in STAGES or item.get("split") not in ALLOWED_SPLITS:
            raise PostTrainingContractError("INVALID_POST_TRAINING_STAGE")
        if REQUIRED_STAGE_FIELDS[item["stage"]] - set(item) or item["stage_id"] in ids:
            raise PostTrainingContractError("INVALID_POST_TRAINING_STAGE_FIELDS")
        if not isinstance(item["row_count"], int) or item["row_count"] <= 0:
            raise PostTrainingContractError("INVALID_POST_TRAINING_ROW_COUNT")
        if item["split"] != "quarantine" and (not item["license_manifest_hash"] or not item["consent_basis"]):
            raise PostTrainingContractError("UNGOVERNED_POST_TRAINING_SOURCE")
        key = (item["stage"], item["source_family"])
        prior = lineage.get(key)
        if prior and prior != item["split"] and {prior, item["split"]} & {"interaction_blind", "sealed"}:
            raise PostTrainingContractError("CROSS_SPLIT_POST_TRAINING_FAMILY")
        lineage[key] = item["split"]
        ids.add(item["stage_id"])
        normalized.append(dict(item))
    if not {"sft", "preference", "safety"}.issubset({item["stage"] for item in normalized if item["split"] == "train"}):
        raise PostTrainingContractError("MISSING_TRAIN_POST_TRAINING_STAGE")
    return tuple(normalized)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
