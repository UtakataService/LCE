import json
from pathlib import Path

import pytest

from lce_validation.runtime.model_pack import PackValidationError, load_pack, lock_profile, recognize_language_pack
from lce_validation.runtime.utterance_frame import frame_utterance


PACK_PATH = Path("lce_validation/fixtures/reference_language_pack_listen_v1.json")


def test_reference_language_pack_matches_legacy_listen_rule_in_english_and_japanese():
    pack = load_pack(PACK_PATH)
    for text in ("Please just listen for a moment.", "今は愚痴を聞いてほしい。"):
        legacy = frame_utterance(text)
        packed = recognize_language_pack(text, pack)
        assert "listen_only" in legacy["cues"]
        assert "legacy.frame.listen_only.v1" in legacy["legacy_rule_ids"]
        assert packed["cues"] == ["listen_only"]
        assert packed["legacy_rule_ids"] == ["legacy.frame.listen_only.v1"]


def test_profile_lock_pins_exact_pack_identity_and_hash():
    pack = load_pack(PACK_PATH)
    profile = {
        "schema_version": "lce-profile/v1", "profile_id": "reference-listen", "profile_version": "1.0.0",
        "engine_compatibility": "lce-core/v1", "capabilities": ["frame.listen_only"],
        "pack_refs": [{"pack_id": pack["pack_id"], "pack_version": pack["pack_version"], "content_hash": pack["content_hash"]}],
    }
    locked = lock_profile(profile, [pack])
    assert locked["profile_lock_hash"].startswith("sha256:")
    assert locked["pack_refs"][0]["content_hash"] == pack["content_hash"]


def test_pack_hash_tampering_fails_closed(tmp_path):
    row = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    row["payload"]["rules"][0]["patterns"].append("tampered")
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PackValidationError, match="PACK_CONTENT_HASH_MISMATCH"):
        load_pack(path)
