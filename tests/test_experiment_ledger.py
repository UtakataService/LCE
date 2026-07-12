from pathlib import Path

import pytest

from lce_validation.runtime.experiment_ledger import (
    ExperimentLedgerError,
    append_experiment_record,
    make_experiment_record,
    read_experiment_ledger,
    release_claim_status,
    verify_experiment_ledger,
)
from lce_validation.runtime.quality_target import load_quality_target


TARGET = load_quality_target("lce_validation/fixtures/lce_20b_quality_target_v1.json")


def _record(*, run_id: str, variant: str = "lm_with_lce", metric_id: str = "dialogue-continuity-v1", split: str = "interaction_blind", parent_hash=None):
    return make_experiment_record(
        run_id=run_id,
        target=TARGET,
        variant=variant,
        model={"model_id": "pilot-100m", "architecture": "decoder-only", "parameter_count": 100_000_000, "tokenizer_hash": "sha256:tokenizer", "code_hash": "sha256:code", "precision": "bf16"},
        data={"dataset_snapshot_hash": "sha256:data", "license_manifest_hash": "sha256:license", "dedup_policy_id": "exact-v1", "language_mix": {"en": 0.8, "ja": 0.2}},
        evaluation={"split": split, "metric_id": metric_id, "value": 0.5, "evaluator_build_hash": "sha256:evaluator"},
        parent_hash=parent_hash,
    )


def test_experiment_ledger_chains_target_pinned_records(tmp_path):
    path = tmp_path / "experiments.jsonl"
    first = _record(run_id="pilot-001")
    append_experiment_record(path, first)
    second = _record(run_id="pilot-002", parent_hash=first["record_hash"])
    append_experiment_record(path, second)

    records = read_experiment_ledger(path)
    assert verify_experiment_ledger(records)["valid"]
    assert records[0]["target_identity"]["snapshot_hash"] == TARGET.snapshot_hash


def test_experiment_ledger_rejects_undeclared_metric_split_pair():
    with pytest.raises(ExperimentLedgerError, match="EVALUATION_NOT_DECLARED_BY_TARGET"):
        _record(run_id="bad", metric_id="dialogue-continuity-v1", split="sealed")


def test_experiment_ledger_detects_tampering(tmp_path):
    path = tmp_path / "experiments.jsonl"
    record = _record(run_id="pilot-001")
    append_experiment_record(path, record)
    records = read_experiment_ledger(path)
    records[0]["model"]["precision"] = "int4"

    assert "record:0:HASH_MISMATCH" in verify_experiment_ledger(records)["violations"]


def test_release_claim_stays_closed_until_all_gates_variants_and_splits_are_complete():
    status = release_claim_status(TARGET, [_record(run_id="only-one")])

    assert not status["publishable"]
    assert "sealed" in status["missing_required_splits"]
    assert set(status["missing_comparison_variants"]) == {"lce_only", "lm_only"}
