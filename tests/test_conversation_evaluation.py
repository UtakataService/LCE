import json
from pathlib import Path

import pytest

from lce_validation.runtime.conversation_contract import ContractError
from lce_validation.runtime.conversation_evaluation import (
    append_ledger_event,
    evaluate_exposed_bank,
    fixture_hash,
    make_ledger_event,
    read_ledger,
    run_interaction_blind_bank,
    validate_split_manifest,
    verify_custody_ledger,
)


def _fixture_rows() -> list[dict]:
    path = Path("lce_validation/fixtures/conversation_orchestrator_phase0_replay.jsonl")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _manifest_row(fixture: dict, *, split: str = "exposed", group: str | None = None) -> dict:
    return {
        "case_id": fixture["case_id"], "semantic_group_id": group or fixture["case_id"],
        "scenario_parent_id": "parent:" + (group or fixture["case_id"]), "lineage_id": "lineage:v1",
        "language": "ja" if fixture["case_id"].endswith("-ja") else "en",
        "language_role": "functional_ja" if fixture["case_id"].endswith("-ja") else "primary_en",
        "family": "conversation", "turn_count": len(fixture["turns"]), "split": split,
        "generation_method": "author_created", "author_role": "Builder", "fixture_hash": fixture_hash(fixture),
    }


def test_exposed_bank_scores_transitions_without_claiming_blind_capability():
    report = evaluate_exposed_bank(_fixture_rows())
    assert report["scope"] == "exposed_only"
    assert report["passed"] == 20
    assert report["failed"] == 0
    assert not report["p0_violations"]


def test_static_exposed_manifest_is_split_valid_and_hashes_its_fixtures():
    manifest_path = Path("lce_validation/fixtures/conversation_orchestrator_phase2_exposed_manifest.jsonl")
    manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    fixtures = {row["case_id"]: row for row in _fixture_rows()}
    validate_split_manifest(manifest)
    assert len(manifest) == len(fixtures) == 20
    assert all(row["fixture_hash"] == fixture_hash(fixtures[row["case_id"]]) for row in manifest)


def test_split_manifest_rejects_translation_siblings_across_splits():
    fixtures = _fixture_rows()[:2]
    rows = [_manifest_row(fixtures[0], split="exposed", group="listen"), _manifest_row(fixtures[1], split="sealed", group="listen")]
    with pytest.raises(ContractError, match="CROSS_SPLIT_SEMANTIC_GROUP"):
        validate_split_manifest(rows)


def test_append_only_custody_chain_and_tampering_are_detected(tmp_path):
    ledger_path = tmp_path / "custody.jsonl"
    first = make_ledger_event(
        event_id="e1", timestamp_utc="2026-07-11T00:00:00Z", actor_role="Builder", action="split",
        artifact_type="fixture_manifest", artifact_id="m1", artifact_hash="sha256:manifest", semantic_group_ids=["g1"],
        split="exposed", parent_event_hash=None, build_hash="sha256:build", config_hash="sha256:config", reason_code="INITIAL_SPLIT",
    )
    append_ledger_event(ledger_path, first)
    second = make_ledger_event(
        event_id="e2", timestamp_utc="2026-07-11T00:01:00Z", actor_role="Evaluator", action="run",
        artifact_type="report", artifact_id="r1", artifact_hash="sha256:report", semantic_group_ids=["g1"],
        split="exposed", parent_event_hash=first["event_hash"], build_hash="sha256:build", config_hash="sha256:config", reason_code="EXPOSED_RUN",
    )
    append_ledger_event(ledger_path, second)
    rows = read_ledger(ledger_path)
    assert verify_custody_ledger(rows)["valid"]
    rows[1]["reason_code"] = "TAMPERED"
    assert "ledger:1:HASH_MISMATCH" in verify_custody_ledger(rows)["violations"]


def test_implementer_view_of_sealed_group_invalidates_custody():
    event = make_ledger_event(
        event_id="e1", timestamp_utc="2026-07-11T00:00:00Z", actor_role="Implementer", action="view",
        artifact_type="fixture", artifact_id="secret", artifact_hash="sha256:fixture", semantic_group_ids=["sealed-group"],
        split="sealed", parent_event_hash=None, build_hash="sha256:build", config_hash="sha256:config", reason_code="DEBUG",
    )
    report = verify_custody_ledger([event])
    assert not report["valid"]
    assert report["compromised_group_hashes"]


def test_blind_runner_requires_splitter_ledger_and_returns_only_case_hashes(tmp_path):
    fixture = _fixture_rows()[0]
    fixture_path = tmp_path / "blind.jsonl"
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = _manifest_row(fixture, split="interaction_blind", group="blind-listen")
    manifest_path = tmp_path / "manifest.jsonl"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")
    custody_path = tmp_path / "custody.jsonl"
    split = make_ledger_event(
        event_id="split", timestamp_utc="2026-07-11T00:00:00Z", actor_role="Splitter", action="split",
        artifact_type="fixture_manifest", artifact_id="blind-manifest", artifact_hash="sha256:manifest", semantic_group_ids=["blind-listen"],
        split="interaction_blind", parent_event_hash=None, build_hash="sha256:build", config_hash="sha256:config", reason_code="BLIND_SPLIT",
    )
    append_ledger_event(custody_path, split)
    report = run_interaction_blind_bank(
        fixtures_path=fixture_path, manifest_path=manifest_path, custody_path=custody_path,
        timestamp_utc="2026-07-11T00:01:00Z", build_hash="sha256:build", config_hash="sha256:config",
    )
    assert report["scope"] == "interaction_blind"
    assert report["case_count"] == 1
    assert fixture["turns"][0]["text"] not in json.dumps(report)
    assert len(read_ledger(custody_path)) == 2
