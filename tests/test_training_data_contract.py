import json
from pathlib import Path

import pytest

from lce_validation.runtime.training_data_contract import TrainingDataContractError, load_corpus_manifest, validate_corpus_manifest


PATH = Path("lce_validation/fixtures/lce_20b_pilot_corpus_manifest_v1.json")


def test_pilot_manifest_requires_en_ja_and_byte_fallback():
    manifest = load_corpus_manifest(PATH)

    assert manifest.language_mix() == {"en": 0.8, "ja": 0.2}
    assert manifest.tokenizer["byte_fallback"] is True
    assert manifest.snapshot_hash.startswith("sha256:")


def test_manifest_rejects_family_shared_by_train_and_sealed():
    raw = json.loads(PATH.read_text(encoding="utf-8"))
    raw["sources"][3]["source_family"] = "en-open-pilot-family"

    with pytest.raises(TrainingDataContractError, match="CROSS_SPLIT_SOURCE_FAMILY"):
        validate_corpus_manifest(raw)


def test_manifest_rejects_tokenizer_without_byte_fallback():
    raw = json.loads(PATH.read_text(encoding="utf-8"))
    raw["tokenizer"]["byte_fallback"] = False

    with pytest.raises(TrainingDataContractError, match="TOKENIZER_REQUIRES_BYTE_FALLBACK"):
        validate_corpus_manifest(raw)
