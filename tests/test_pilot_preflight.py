import json
from pathlib import Path

import pytest

from lce_validation.runtime.pilot_preflight import PilotPreflightError, validate_pilot_preflight
from lce_validation.runtime.quality_target import load_quality_target
from lce_validation.runtime.training_data_contract import load_corpus_manifest


TARGET = load_quality_target("lce_validation/fixtures/lce_20b_quality_target_v1.json")
CORPUS = load_corpus_manifest("lce_validation/fixtures/lce_20b_pilot_corpus_manifest_v1.json")
PATH = Path("lce_validation/fixtures/lce_100m_pilot_preflight_v1.json")


def _preflight():
    raw = json.loads(PATH.read_text(encoding="utf-8"))
    raw["target_snapshot_hash"] = TARGET.snapshot_hash
    raw["corpus_snapshot_hash"] = CORPUS.snapshot_hash
    return raw


def test_100m_pilot_preflight_is_pinned_to_target_and_corpus():
    pilot = validate_pilot_preflight(_preflight(), target=TARGET, corpus=CORPUS)

    assert pilot.parameter_count == 100_000_000
    assert pilot.declared_variant == "lm_only"


def test_preflight_rejects_a_20b_run_before_small_pilot_gates():
    raw = _preflight()
    raw["parameter_count"] = 20_000_000_000

    with pytest.raises(PilotPreflightError, match="PILOT_PARAMETER_TIER_NOT_ALLOWED"):
        validate_pilot_preflight(raw, target=TARGET, corpus=CORPUS)


def test_preflight_rejects_corpus_provenance_drift():
    raw = _preflight()
    raw["corpus_snapshot_hash"] = "sha256:other"

    with pytest.raises(PilotPreflightError, match="PILOT_PROVENANCE_SNAPSHOT_MISMATCH"):
        validate_pilot_preflight(raw, target=TARGET, corpus=CORPUS)
