import json
from pathlib import Path

import pytest

from lce_validation.runtime.quality_target import QualityTargetError, load_quality_target, validate_quality_target


TARGET_PATH = Path("lce_validation/fixtures/lce_20b_quality_target_v1.json")


def test_reference_20b_quality_target_has_all_tracks_and_comparison_variants():
    target = load_quality_target(TARGET_PATH)

    assert target.planned_tracks() == {"dialogue", "knowledge", "reasoning", "coding", "safety", "bilingual"}
    assert set(target.comparison_variants) == {"lce_only", "lm_only", "lm_with_lce"}
    assert not target.release_ready()
    assert target.trace_identity()["snapshot_hash"].startswith("sha256:")


def test_target_rejects_missing_lce_ablation_variant():
    raw = json.loads(TARGET_PATH.read_text(encoding="utf-8"))
    raw["comparison_variants"] = ["lce_only", "lm_only"]

    with pytest.raises(QualityTargetError, match="INVALID_COMPARISON_VARIANTS"):
        validate_quality_target(raw)


def test_target_rejects_release_plan_without_sealed_gate():
    raw = json.loads(TARGET_PATH.read_text(encoding="utf-8"))
    raw["release_gates"] = [
        {"gate_id": "blind-only", "requires_split": "interaction_blind", "status": "planned", "failure_action": "no claim"}
    ]

    with pytest.raises(QualityTargetError, match="MISSING_SEALED_RELEASE_GATE"):
        validate_quality_target(raw)
