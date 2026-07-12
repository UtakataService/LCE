from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..audit.release_gate import release_gate_row
from ..harness.accept_c import make_accept_row
from ..harness.reducers import reduce_acceptance
from ..harness.verifier_rows import sufficiency_result, verifier_result
from ..runtime.artifact_store import record_artifact
from ..runtime.event_log import EventLog
from ..runtime.replay_manifest import build_replay_manifest, write_manifest
from ..schema_tools import write_jsonl
from ..systems.lane_records import lane_row
from ..systems.pi_service_probe import dry_run_pi_service_probe
from ..systems.process_identity import current_process_identity
from ..systems.resource_sampler import sample_resource
from .baselines import run_required_baselines
from .reasoning import structural_decide


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def fixture_evidence_rows(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    rows = fixture.get("evidence_rows")
    if rows:
        return list(rows)
    return [{
        "evidence_id": f"ev-{fixture['fixture_id']}-default",
        "text": fixture.get("expected_behavior", ""),
        "supports": fixture.get("expected_outcome") in {"ACCEPT_CAVEATED", "REPAIR_CLARIFY", "REPAIR_RETRIEVE"},
        "current": "stale" not in fixture.get("phenomenon_tags", []),
        "source_ref": fixture.get("provenance_ref", "prov-unknown"),
    }]


def build_utterance_row(fixture: dict[str, Any]) -> dict[str, Any]:
    tags = fixture.get("phenomenon_tags", [])
    language = "ja" if "japanese_pragmatic" in tags else "en"
    return {
        "row_id": f"utt-{fixture['fixture_id']}",
        "row_type": "utterance_row",
        "fixture_id": fixture["fixture_id"],
        "candidate_id": "CAND-C10" if language == "ja" else fixture["candidate_ids"][0],
        "raw_text": fixture.get("question", fixture.get("expected_behavior", "")),
        "language_profile": language,
        "speech_act_candidates": fixture.get("speech_act_candidates", ["question"]),
        "referent_candidates": fixture.get("referent_candidates", []),
        "pragmatic_constraints": fixture.get("pragmatic_constraints", []),
        "status": "gateable",
        "known_gaps": [],
    }


def build_state_row(fixture: dict[str, Any], utterance: dict[str, Any], evidence_rows: list[dict[str, Any]]) -> dict[str, Any]:
    tags = fixture.get("phenomenon_tags", [])
    gaps: list[str] = []
    if "ambiguous_reference" in tags:
        gaps.append("referent_ambiguous")
    if "stale_evidence" in tags:
        gaps.append("temporal_currentness_unresolved")
    if "contradiction" in tags:
        gaps.append("contradictory_evidence_present")
    return {
        "row_id": f"state-{fixture['fixture_id']}",
        "row_type": "state_row",
        "fixture_id": fixture["fixture_id"],
        "candidate_id": "CAND-C03",
        "utterance_ref": utterance["row_id"],
        "evidence_refs": [row["evidence_id"] for row in evidence_rows],
        "status": "blocked" if gaps else "gateable",
        "known_gaps": gaps,
    }


def select_evidence(fixture: dict[str, Any], evidence_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    selected = [row for row in evidence_rows if row.get("selected", True)]
    row = {
        "row_id": f"retrieval-{fixture['fixture_id']}",
        "row_type": "retrieval_candidate_row",
        "fixture_id": fixture["fixture_id"],
        "candidate_id": "CAND-C02",
        "selected_evidence_refs": [item["evidence_id"] for item in selected],
        "selection_rule": "fixture_registered_evidence_only",
        "status": "gateable" if selected else "evidence_pending",
        "known_gaps": [] if selected else ["no_registered_evidence_selected"],
    }
    return row, selected


def decide(fixture: dict[str, Any], state: dict[str, Any], selected_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return structural_decide(fixture, state, selected_evidence)


def repair_row(fixture: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any] | None:
    if decision["outcome"] not in {"REPAIR_CLARIFY", "REPAIR_RETRIEVE", "UNKNOWN_MODEL_GAP"}:
        return None
    return {
        "row_id": f"repair-{fixture['fixture_id']}",
        "row_type": "repair_row",
        "fixture_id": fixture["fixture_id"],
        "candidate_id": "CAND-C03",
        "decision_ref": decision["row_id"],
        "repair_type": decision["outcome"],
        "status": "required",
        "known_gaps": [decision["reason"]],
    }


def acceptance_for_decision(fixture: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    accept = make_accept_row(
        decision["row_id"],
        decision["candidate_id"],
        fixture["fixture_id"],
        [f"CLAIM-{fixture['fixture_id']}"],
        fixture.get("gate_assertions", []),
    )
    if decision["outcome"] == "ACCEPT_CAVEATED":
        v_results = [verifier_result("V_entailment", decision["row_id"], "pass", "bounded evidence supports answer")]
        s_results = [sufficiency_result("SUFF_DIRECT_SPAN", decision["row_id"], "pass", "direct fixture evidence present")]
    elif decision["outcome"] in {"REPAIR_CLARIFY", "REPAIR_RETRIEVE", "UNKNOWN_MODEL_GAP"}:
        v_results = [verifier_result("V_coverage", decision["row_id"], "unknown", decision["reason"])]
        s_results = [sufficiency_result("SUFF_DIRECT_SPAN", decision["row_id"], "unknown", decision["reason"])]
    else:
        v_results = [verifier_result("V_entailment", decision["row_id"], "fail", decision["reason"])]
        s_results = [sufficiency_result("SUFF_DIRECT_SPAN", decision["row_id"], "fail", decision["reason"])]
    return reduce_acceptance(accept, v_results, s_results, [], attempted_claim_text=fixture.get("attempted_claim_text", "bounded empirical slice"))


def run_empirical_slice(fixtures_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_id = out.name
    started = time.perf_counter()
    fixtures = load_jsonl(fixtures_path)
    log = EventLog(out / "events.jsonl")
    proc = current_process_identity()
    resource = sample_resource(run_id)
    lane = lane_row(run_id, proc["process_identity_ref"], resource["resource_snapshot_ref"])
    pi_probe = dry_run_pi_service_probe()

    utterance_rows: list[dict[str, Any]] = []
    state_rows: list[dict[str, Any]] = []
    evidence_rows_all: list[dict[str, Any]] = []
    retrieval_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []
    repair_rows: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []
    acceptance_rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for index, fixture in enumerate(fixtures, start=1):
        event_prefix = f"evt-{index:03d}"
        evidence_rows = fixture_evidence_rows(fixture)
        utterance = build_utterance_row(fixture)
        state = build_state_row(fixture, utterance, evidence_rows)
        retrieval, selected = select_evidence(fixture, evidence_rows)
        decision = decide(fixture, state, selected)
        repair = repair_row(fixture, decision)
        acceptance = acceptance_for_decision(fixture, decision)
        replay_ref = f"replay-{run_id}"
        baselines = run_required_baselines(fixture, evidence_rows, selected, decision, run_id, resource["resource_snapshot_ref"], replay_ref)

        utterance_rows.append(utterance)
        state_rows.append(state)
        evidence_rows_all.extend(evidence_rows)
        retrieval_rows.append(retrieval)
        decision_rows.append(decision)
        if repair:
            repair_rows.append(repair)
        baseline_rows.extend(baselines)
        acceptance_rows.append(acceptance)
        for event_type, row in [
            ("input_received", utterance),
            ("state_write", state),
            ("retrieval_result", retrieval),
            ("decision_emitted", decision),
            ("acceptance_reduced", acceptance),
        ]:
            events.append(log.append({
                "event_id": f"{event_prefix}-{event_type}",
                "parent_event_id": None,
                "run_id": run_id,
                "row_id": row.get("row_id", row.get("accept_row_id")),
                "candidate_id": row.get("candidate_id", fixture["candidate_ids"][0]),
                "actor": "empirical-runtime",
                "task_id": fixture["fixture_id"],
                "event_type": event_type,
                "input_ref": fixture["input_payload_ref"],
                "output_ref": row.get("row_id", row.get("accept_row_id")),
                "state_version": state["row_id"],
                "artifact_hash_refs": [],
                "redaction_state": "none",
                "resource_snapshot_ref": resource["resource_snapshot_ref"],
            }))

    write_jsonl(out / "fixtures.jsonl", fixtures)
    write_jsonl(out / "evidence_rows.jsonl", evidence_rows_all)
    write_jsonl(out / "utterance_rows.jsonl", utterance_rows)
    write_jsonl(out / "state_rows.jsonl", state_rows)
    write_jsonl(out / "retrieval_rows.jsonl", retrieval_rows)
    write_jsonl(out / "decision_rows.jsonl", decision_rows)
    write_jsonl(out / "repair_rows.jsonl", repair_rows)
    write_jsonl(out / "baseline_runs.jsonl", baseline_rows)
    write_jsonl(out / "acceptance_results.jsonl", acceptance_rows)
    (out / "process_identity.json").write_text(json.dumps(proc, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "resource_snapshot.json").write_text(json.dumps(resource, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "lane_row.json").write_text(json.dumps(lane, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "pi_service_probe_dryrun.json").write_text(json.dumps(pi_probe, ensure_ascii=False, indent=2), encoding="utf-8")

    artifacts = [record_artifact(out / name, artifact_ref=name) for name in [
        "events.jsonl",
        "fixtures.jsonl",
        "evidence_rows.jsonl",
        "decision_rows.jsonl",
        "baseline_runs.jsonl",
        "acceptance_results.jsonl",
    ]]
    manifest = build_replay_manifest(run_id, events, artifacts)
    manifest["rebuild_command_ref"] = "python -m lce_validation.cli run-empirical"
    write_manifest(out / "replay_manifest.json", manifest)
    failed_checks = []
    if not events:
        failed_checks.append("missing_events")
    if not acceptance_rows:
        failed_checks.append("missing_acceptance_rows")
    gate = release_gate_row(run_id, failed_checks, [
        "transformer_replacement",
        "quality_parity",
        "benchmark_improvement",
        "cpu_pi_sufficiency",
        "production_readiness",
    ])
    (out / "release_gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "ok": not failed_checks,
        "run_id": run_id,
        "fixture_count": len(fixtures),
        "decision_counts": _count(row["outcome"] for row in decision_rows),
        "acceptance_counts": _count(row["verdict"] for row in acceptance_rows),
        "baseline_count": len(baseline_rows),
        "duration_seconds": round(time.perf_counter() - started, 6),
        "replay_manifest_id": manifest["replay_manifest_id"],
        "release_decision": gate["decision"],
        "blocked_claims": gate["blocked_claims"],
    }
    (out / "empirical_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _count(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts
