from __future__ import annotations

import json

from scripts.verify_holdout_manifest import MANIFEST_PATH, validate


def test_public_holdout_manifest_is_complete_and_metadata_only() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert validate(manifest) == []
    assert manifest["total_case_count"] == 125
    assert sum(track["case_count"] for track in manifest["tracks"]) == 125


def test_public_holdout_manifest_has_no_case_payload_or_gold() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    serialized = json.dumps(manifest, sort_keys=True).lower()

    for forbidden in ('"cases"', '"case_text"', '"prompt"', '"expected"', '"gold"'):
        assert forbidden not in serialized
