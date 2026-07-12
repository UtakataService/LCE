import json
from pathlib import Path

import pytest

from lce_validation.runtime.post_training_contract import PostTrainingContractError, load_post_training_manifest, validate_post_training_manifest


PATH = Path("lce_validation/fixtures/lce_post_training_manifest_v1.json")


def test_post_training_manifest_requires_all_training_stages():
    manifest = load_post_training_manifest(PATH)

    assert manifest.train_stages() == ("sft", "preference", "safety")
    assert manifest.snapshot_hash.startswith("sha256:")


def test_post_training_manifest_rejects_missing_safety_stage():
    raw = json.loads(PATH.read_text(encoding="utf-8"))
    raw["stages"] = [stage for stage in raw["stages"] if stage["stage"] != "safety"]

    with pytest.raises(PostTrainingContractError, match="MISSING_TRAIN_POST_TRAINING_STAGE"):
        validate_post_training_manifest(raw)


def test_post_training_manifest_rejects_sealed_family_reused_by_train():
    raw = json.loads(PATH.read_text(encoding="utf-8"))
    raw["stages"][3]["source_family"] = "safety-en-ja"

    with pytest.raises(PostTrainingContractError, match="CROSS_SPLIT_POST_TRAINING_FAMILY"):
        validate_post_training_manifest(raw)
