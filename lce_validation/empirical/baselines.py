from __future__ import annotations

from typing import Any


def _tokens(text: str) -> set[str]:
    return {part.strip(".,:;!?()[]{}\"'").lower() for part in text.split() if part.strip()}


def run_b0_unknown(fixture: dict[str, Any], run_id: str, resource_ref: str, replay_ref: str) -> dict[str, Any]:
    return {
        "baseline_run_id": f"baseline-{run_id}-{fixture['fixture_id']}-B0",
        "baseline_id": "DATA-B0",
        "fixture_id": fixture["fixture_id"],
        "candidate_id": fixture["candidate_ids"][0],
        "run_id": run_id,
        "lane_label": "WIN_CPU_FIRST",
        "result_ref": "UNKNOWN_MODEL_GAP",
        "failure_profile": "always_unknown_or_reject_baseline",
        "resource_snapshot_ref": resource_ref,
        "replay_manifest_ref": replay_ref,
        "adjudication_status": "baseline_only",
        "block_condition_triggered": True,
    }


def run_b1_keyword(fixture: dict[str, Any], evidence_rows: list[dict[str, Any]], run_id: str, resource_ref: str, replay_ref: str) -> dict[str, Any]:
    query_tokens = _tokens(fixture.get("question", ""))
    best_score = 0
    for evidence in evidence_rows:
        best_score = max(best_score, len(query_tokens & _tokens(evidence.get("text", ""))))
    result = "candidate_evidence_found" if best_score > 0 else "UNKNOWN_MODEL_GAP"
    return {
        "baseline_run_id": f"baseline-{run_id}-{fixture['fixture_id']}-B1",
        "baseline_id": "DATA-B1",
        "fixture_id": fixture["fixture_id"],
        "candidate_id": fixture["candidate_ids"][0],
        "run_id": run_id,
        "lane_label": "WIN_CPU_FIRST",
        "result_ref": result,
        "failure_profile": f"keyword_overlap_score={best_score}; entailment_not_checked",
        "resource_snapshot_ref": resource_ref,
        "replay_manifest_ref": replay_ref,
        "adjudication_status": "baseline_only",
        "block_condition_triggered": result != fixture.get("expected_outcome"),
    }


def run_b2_rule(fixture: dict[str, Any], selected_evidence: list[dict[str, Any]], decision: dict[str, Any], run_id: str, resource_ref: str, replay_ref: str) -> dict[str, Any]:
    result = decision["outcome"] if selected_evidence else "UNKNOWN_MODEL_GAP"
    return {
        "baseline_run_id": f"baseline-{run_id}-{fixture['fixture_id']}-B2",
        "baseline_id": "DATA-B2",
        "fixture_id": fixture["fixture_id"],
        "candidate_id": fixture["candidate_ids"][0],
        "run_id": run_id,
        "lane_label": "WIN_CPU_FIRST",
        "result_ref": result,
        "failure_profile": "rule_only_entailment_proxy; no neural semantic mixing",
        "resource_snapshot_ref": resource_ref,
        "replay_manifest_ref": replay_ref,
        "adjudication_status": "bounded_rule_check",
        "block_condition_triggered": result != fixture.get("expected_outcome"),
    }


def run_required_baselines(
    fixture: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    selected_evidence: list[dict[str, Any]],
    decision: dict[str, Any],
    run_id: str,
    resource_ref: str,
    replay_ref: str,
) -> list[dict[str, Any]]:
    return [
        run_b0_unknown(fixture, run_id, resource_ref, replay_ref),
        run_b1_keyword(fixture, evidence_rows, run_id, resource_ref, replay_ref),
        run_b2_rule(fixture, selected_evidence, decision, run_id, resource_ref, replay_ref),
    ]
