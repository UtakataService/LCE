from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit.redline_scan import scan_path
from .audit.release_gate import release_gate_row
from .empirical.engine import run_empirical_slice
from .empirical.baseline_comparison import run_baseline_comparison
from .empirical.chunked_dialogue import respond_from_chunk_seeds, run_chunked_dialogue_benchmark
from .empirical.candidate_assurance_benchmark import run_candidate_assurance_benchmark
from .empirical.acceptance_challenge_benchmark import run_acceptance_challenge_benchmark
from .empirical.public_readiness_evidence import run_public_readiness_evidence
from .empirical.reference_performance import run_reference_performance
from .empirical.quality_discovery_campaign import run_quality_discovery_campaign
from .empirical.quality_discovery_aggregate import run_quality_discovery_aggregate
from .empirical.grading_assurance_benchmark import run_grading_assurance_benchmark
from .empirical.coding_task_runner import run_coding_task, run_coding_task_benchmark
from .empirical.fixture_bank import generate_fixture_bank
from .empirical.history_chunked_dialogue import respond_with_history_chunks, run_history_chunked_dialogue_benchmark
from .empirical.hardware_benchmark_validation import run_hardware_benchmark_validation
from .empirical.limited_domain_app import answer_limited_domain
from .empirical.measurement_series import run_measurement_series
from .empirical.natural_language_benchmark import run_natural_language_benchmark
from .empirical.policy_pack_lifecycle import run_policy_pack_lifecycle_benchmark
from .empirical.rule_grounding import run_rule_grounding_benchmark
from .empirical.rule_composition import run_rule_composition_benchmark
from .empirical.semantic_chunk import parse_semantic_chunks, run_semantic_chunk_benchmark
from .empirical.sparse_attention import run_sparse_attention_benchmark
from .empirical.structured_assurance_benchmark import run_structured_assurance_benchmark
from .empirical.neural_candidate import generate_neural_candidates, run_neural_candidate_benchmark
from .empirical.graph_reasoning import run_graph_reasoning, run_graph_reasoning_benchmark
from .empirical.adaptive_renderer import render_verified_response, run_profile_validation_benchmark, run_renderer_benchmark
from .empirical.seeded_dialogue import respond_from_seed, run_seeded_dialogue_benchmark
from .empirical.small_model_adapter import run_small_model_adapter
from .empirical.topic_continuity_dialogue import respond_with_topic_continuity, run_topic_continuity_benchmark
from .harness.accept_c import make_accept_row
from .harness.reducers import reduce_acceptance
from .harness.verifier_rows import sufficiency_result, verifier_result
from .runtime.artifact_store import record_artifact
from .runtime.event_log import EventLog
from .runtime.replay_manifest import build_replay_manifest, write_manifest
from .schema_tools import load_json, validate_jsonl, validate_row, write_jsonl
from .systems.lane_records import lane_row
from .systems.pi_service_probe import dry_run_pi_service_probe
from .systems.process_identity import current_process_identity
from .systems.resource_sampler import sample_resource


PACKAGE_ROOT = Path(__file__).resolve().parent


def _schema(name: str) -> dict:
    return load_json(PACKAGE_ROOT / "schemas" / name)


def validate_schema(target: str) -> int:
    target_path = Path(target)
    checks = [
        (PACKAGE_ROOT / "fixtures" / "seed_fixtures.jsonl", _schema("fixture.schema.json")),
        (PACKAGE_ROOT / "fixtures" / "seed_baselines.jsonl", _schema("baseline_run.schema.json")),
    ]
    if target_path.exists() and target_path.is_file() and target_path.suffix == ".jsonl":
        checks = [(target_path, _schema("fixture.schema.json"))]
    errors: list[str] = []
    for path, schema in checks:
        errors.extend(validate_jsonl(path, schema))
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "checked": [str(path) for path, _ in checks]}, ensure_ascii=False, indent=2))
    return 0


def run_smoke(out: str) -> int:
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = out_dir.name
    log = EventLog(out_dir / "events.jsonl")
    proc = current_process_identity()
    res = sample_resource(run_id)
    lane = lane_row(run_id, proc["process_identity_ref"], res["resource_snapshot_ref"])
    pi_probe = dry_run_pi_service_probe()
    events = [
        log.append({"event_id": "evt-001", "parent_event_id": None, "run_id": run_id, "row_id": "RT-001", "candidate_id": "CAND-C08", "actor": "cli", "task_id": "smoke", "event_type": "input_received", "input_ref": "seed", "output_ref": None, "state_version": "state-0", "artifact_hash_refs": [], "redaction_state": "none"}),
        log.append({"event_id": "evt-002", "parent_event_id": "evt-001", "run_id": run_id, "row_id": "SYS-001", "candidate_id": "CAND-C07", "actor": "cli", "task_id": "smoke", "event_type": "resource_snapshot", "input_ref": None, "output_ref": res["resource_snapshot_ref"], "state_version": "state-0", "artifact_hash_refs": [], "redaction_state": "none", "resource_snapshot_ref": res["resource_snapshot_ref"]}),
    ]
    (out_dir / "process_identity.json").write_text(json.dumps(proc, indent=2), encoding="utf-8")
    (out_dir / "resource_snapshot.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    (out_dir / "lane_row.json").write_text(json.dumps(lane, indent=2), encoding="utf-8")
    (out_dir / "pi_service_probe_dryrun.json").write_text(json.dumps(pi_probe, indent=2), encoding="utf-8")
    artifacts = [record_artifact(out_dir / "events.jsonl", artifact_ref="events")]
    manifest = build_replay_manifest(run_id, events, artifacts)
    write_manifest(out_dir / "replay_manifest.json", manifest)
    print(json.dumps({"ok": True, "out": str(out_dir), "replay_manifest_id": manifest["replay_manifest_id"]}, ensure_ascii=False, indent=2))
    return 0


def run_empirical(fixtures: str, out: str) -> int:
    summary = run_empirical_slice(fixtures, out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


def generate_fixture_bank_cmd(out: str, per_family: int) -> int:
    rows = generate_fixture_bank(per_family)
    write_jsonl(out, rows)
    print(json.dumps({"ok": True, "out": out, "fixture_count": len(rows), "per_family": per_family}, ensure_ascii=False, indent=2))
    return 0


def baseline_comparison_cmd(fixtures: str, out: str) -> int:
    summary = run_baseline_comparison(fixtures, out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


def small_model_adapter_cmd(fixtures: str, out: str, mode: str, model_id: str) -> int:
    summary = run_small_model_adapter(fixtures, out, mode=mode, model_id=model_id)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


def measurement_series_cmd(fixtures: str, out: str, repeats: int) -> int:
    summary = run_measurement_series(fixtures, out, repeats=repeats)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


def answer_limited_domain_cmd(fixtures: str, query: str, out: str | None) -> int:
    result = answer_limited_domain(fixtures, query, out_path=out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def hardware_benchmark_validation_cmd(fixtures: str, out: str, repeats: int) -> int:
    result = run_hardware_benchmark_validation(fixtures, out, repeats=repeats)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def natural_language_benchmark_cmd(fixtures: str, benchmark: str, out: str) -> int:
    result = run_natural_language_benchmark(fixtures, benchmark, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def rule_grounding_benchmark_cmd(cases: str, out: str) -> int:
    result = run_rule_grounding_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def rule_composition_benchmark_cmd(cases: str, out: str) -> int:
    result = run_rule_composition_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def policy_pack_lifecycle_benchmark_cmd(cases: str, out: str) -> int:
    result = run_policy_pack_lifecycle_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def seeded_dialogue_cmd(text: str, out: str | None) -> int:
    result = respond_from_seed(text)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def seeded_dialogue_benchmark_cmd(cases: str, out: str) -> int:
    result = run_seeded_dialogue_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def chunked_dialogue_cmd(text: str, out: str | None) -> int:
    result = respond_from_chunk_seeds(text)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def chunked_dialogue_benchmark_cmd(cases: str, out: str) -> int:
    result = run_chunked_dialogue_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def history_chunked_dialogue_cmd(text: str, history_file: str | None, out: str | None) -> int:
    history = []
    if history_file:
        history = json.loads(Path(history_file).read_text(encoding="utf-8"))
    result = respond_with_history_chunks(text, history)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def history_chunked_dialogue_benchmark_cmd(cases: str, out: str) -> int:
    result = run_history_chunked_dialogue_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def topic_continuity_dialogue_cmd(text: str, history_file: str | None, out: str | None) -> int:
    history = []
    if history_file:
        history = json.loads(Path(history_file).read_text(encoding="utf-8"))
    result = respond_with_topic_continuity(text, history)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def topic_continuity_benchmark_cmd(cases: str, out: str) -> int:
    result = run_topic_continuity_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def coding_task_cmd(prompt: str, history_file: str | None, out: str | None) -> int:
    history = []
    if history_file:
        history = json.loads(Path(history_file).read_text(encoding="utf-8"))
    result = run_coding_task(prompt, history)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def coding_task_benchmark_cmd(cases: str, out: str) -> int:
    result = run_coding_task_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def semantic_chunk_cmd(text: str, language_hint: str, out: str | None) -> int:
    result = parse_semantic_chunks(text, language_hint=language_hint)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def semantic_chunk_benchmark_cmd(cases: str, out: str) -> int:
    result = run_semantic_chunk_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def sparse_attention_benchmark_cmd(cases: str, out: str) -> int:
    result = run_sparse_attention_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def neural_candidate_cmd(text: str, backend: str, model_id: str, out: str | None) -> int:
    result = generate_neural_candidates(text, backend=backend, model_id=model_id)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def neural_candidate_benchmark_cmd(cases: str, out: str, backend: str, model_id: str) -> int:
    result = run_neural_candidate_benchmark(cases, out, backend=backend, model_id=model_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def graph_reasoning_cmd(text: str, history_file: str | None, out: str | None) -> int:
    history = json.loads(Path(history_file).read_text(encoding="utf-8")) if history_file else []
    result = run_graph_reasoning(text, history)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def graph_reasoning_benchmark_cmd(cases: str, out: str) -> int:
    result = run_graph_reasoning_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def adaptive_render_cmd(text: str, history_file: str | None, profile: str, profile_file: str | None, out: str | None) -> int:
    history = json.loads(Path(history_file).read_text(encoding="utf-8")) if history_file else []
    selected_profile: str | dict[str, Any] = json.loads(Path(profile_file).read_text(encoding="utf-8")) if profile_file else profile
    result = render_verified_response(text, history, profile=selected_profile)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def renderer_benchmark_cmd(cases: str, out: str, split: str) -> int:
    result = run_renderer_benchmark(cases, out, split=split)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def profile_validation_benchmark_cmd(cases: str, out: str) -> int:
    result = run_profile_validation_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def structured_assurance_benchmark_cmd(cases: str, out: str) -> int:
    result = run_structured_assurance_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def candidate_assurance_benchmark_cmd(cases: str, out: str) -> int:
    result = run_candidate_assurance_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def acceptance_challenge_benchmark_cmd(cases: str, out: str) -> int:
    result = run_acceptance_challenge_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def public_readiness_evidence_cmd(out: str) -> int:
    result = run_public_readiness_evidence(out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def reference_performance_cmd(out: str, repeats: int) -> int:
    result = run_reference_performance(out, repeats=repeats)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def quality_discovery_campaign_cmd(cases: str, out: str) -> int:
    result = run_quality_discovery_campaign(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def quality_discovery_aggregate_cmd(out: str) -> int:
    result = run_quality_discovery_aggregate(out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def grading_assurance_benchmark_cmd(cases: str, out: str) -> int:
    result = run_grading_assurance_benchmark(cases, out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def unknown_language_cmd(
    text: str,
    language_hint: str,
    session_file: str | None,
    session_out: str | None,
    out: str | None,
) -> int:
    import importlib
    import inspect

    session = json.loads(Path(session_file).read_text(encoding="utf-8")) if session_file else {}
    module = None
    attempted_modules = (
        "lce_validation.empirical.unknown_language_runtime",
        "lce_validation.empirical.unknown_language",
    )
    for module_name in attempted_modules:
        try:
            module = importlib.import_module(module_name)
            break
        except ModuleNotFoundError as exc:
            if exc.name != module_name:
                raise

    handler = None
    if module is not None:
        for name in (
            "process_unknown_language_turn",
            "respond_unknown_language",
            "run_unknown_language",
            "analyze_unknown_language",
        ):
            candidate = getattr(module, name, None)
            if callable(candidate):
                handler = candidate
                break

    if handler is None:
        result = {
            "ok": False,
            "status": "runtime_unavailable",
            "error": "unknown-language runtime API is not installed",
            "attempted_modules": list(attempted_modules),
        }
    else:
        available = {
            "text": text,
            "language_hint": language_hint,
            "session": session,
            "session_state": session,
            "state": session,
        }
        signature = inspect.signature(handler)
        kwargs = {name: available[name] for name in signature.parameters if name in available}
        result = handler(**kwargs)
        if not isinstance(result, dict):
            raise TypeError("unknown-language runtime must return a dict")
        result.setdefault("ok", True)

    if session_out and result.get("ok"):
        next_session = result.get("session_state", result.get("session", result.get("state")))
        if next_session is not None:
            path = Path(session_out)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(next_session, ensure_ascii=False, indent=2), encoding="utf-8")
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    try:
        print(rendered)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(rendered.encode("utf-8") + b"\n")
    return 0 if result.get("ok") else 1


def reduce_acceptance_cmd(run_dir: str) -> int:
    accept = make_accept_row("RT-001", "CAND-C08", "FX-DATA-F-F-001", ["CLAIM-TRACE"], ["M5"])
    v_results = [verifier_result("V_resource", "RT-001", "unknown", "resource evidence is dry-run only")]
    s_results = [sufficiency_result("SUFF_TRACE_FAITHFUL", "RT-001", "unknown", "trace faithfulness not established")]
    reduced = reduce_acceptance(accept, v_results, s_results, [], attempted_claim_text="trace is available")
    out = Path(run_dir) / "acceptance_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reduced, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(reduced, ensure_ascii=False, indent=2))
    return 0


def scan_redlines(target: str) -> int:
    rows = scan_path(target)
    print(json.dumps({"ok": True, "violations": rows}, ensure_ascii=False, indent=2))
    return 1 if rows else 0


def summarize_release(run_dir: str) -> int:
    failed = []
    run = Path(run_dir)
    if not (run / "replay_manifest.json").exists():
        failed.append("missing_replay_manifest")
    gate = release_gate_row(run.name, failed, ["production_readiness", "feasibility", "replacement"])
    (run / "release_gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    return 0 if gate["decision"] != "not_ready" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate-schema")
    p.add_argument("target", nargs="?", default="samples")
    p = sub.add_parser("run-smoke")
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-empirical")
    p.add_argument("--fixtures", default=str(PACKAGE_ROOT / "fixtures" / "empirical_poc_fixtures.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("generate-fixture-bank")
    p.add_argument("--out", default=str(PACKAGE_ROOT / "fixtures" / "expanded_fixture_bank.jsonl"))
    p.add_argument("--per-family", type=int, default=10)
    p = sub.add_parser("run-baseline-comparison")
    p.add_argument("--fixtures", default=str(PACKAGE_ROOT / "fixtures" / "expanded_fixture_bank.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-small-model-adapter")
    p.add_argument("--fixtures", default=str(PACKAGE_ROOT / "fixtures" / "expanded_fixture_bank.jsonl"))
    p.add_argument("--out", required=True)
    p.add_argument("--mode", choices=["no_run", "dry_run"], default="no_run")
    p.add_argument("--model-id", default="unconfigured")
    p = sub.add_parser("run-measurement-series")
    p.add_argument("--fixtures", default=str(PACKAGE_ROOT / "fixtures" / "expanded_fixture_bank.jsonl"))
    p.add_argument("--out", required=True)
    p.add_argument("--repeats", type=int, default=3)
    p = sub.add_parser("answer-limited-domain")
    p.add_argument("--fixtures", default=str(PACKAGE_ROOT / "fixtures" / "expanded_fixture_bank.jsonl"))
    p.add_argument("--query", required=True)
    p.add_argument("--out")
    p = sub.add_parser("run-hardware-benchmark-validation")
    p.add_argument("--fixtures", default=str(PACKAGE_ROOT / "fixtures" / "expanded_fixture_bank.jsonl"))
    p.add_argument("--out", required=True)
    p.add_argument("--repeats", type=int, default=3)
    p = sub.add_parser("run-natural-language-benchmark")
    p.add_argument("--fixtures", default=str(PACKAGE_ROOT / "fixtures" / "expanded_fixture_bank.jsonl"))
    p.add_argument("--benchmark", default=str(PACKAGE_ROOT / "fixtures" / "natural_language_english_benchmark.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-rule-grounding-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "rule_grounding_step1_cases.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-rule-composition-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "rule_grounding_step2_multirule_cases.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-policy-pack-lifecycle-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "policy_pack_lifecycle_cases.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("seeded-dialogue")
    p.add_argument("--text", required=True)
    p.add_argument("--out")
    p = sub.add_parser("run-seeded-dialogue-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "seeded_dialogue_cases.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("chunked-dialogue")
    p.add_argument("--text", required=True)
    p.add_argument("--out")
    p = sub.add_parser("run-chunked-dialogue-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "chunked_dialogue_cases.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("history-chunked-dialogue")
    p.add_argument("--text", required=True)
    p.add_argument("--history-file")
    p.add_argument("--out")
    p = sub.add_parser("run-history-chunked-dialogue-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "history_chunked_dialogue_cases.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("topic-continuity-dialogue")
    p.add_argument("--text", required=True)
    p.add_argument("--history-file")
    p.add_argument("--out")
    p = sub.add_parser("run-topic-continuity-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "topic_continuity_cases.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("coding-task")
    p.add_argument("--prompt", required=True)
    p.add_argument("--history-file")
    p.add_argument("--out")
    p = sub.add_parser("run-coding-task-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "coding_task_cases.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("semantic-chunk")
    p.add_argument("--text", required=True)
    p.add_argument("--language-hint", choices=["auto", "en", "ja", "mixed"], default="auto")
    p.add_argument("--out")
    p = sub.add_parser("run-semantic-chunk-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "semantic_chunk_v1_cases.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-sparse-attention-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "sparse_attention_v2_cases.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("neural-candidate")
    p.add_argument("--text", required=True)
    p.add_argument("--backend", choices=["heuristic", "ollama_embedding"], default="heuristic")
    p.add_argument("--model-id", default="bge-m3:latest")
    p.add_argument("--out")
    p = sub.add_parser("run-neural-candidate-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "neural_candidate_v3_cases.jsonl"))
    p.add_argument("--out", required=True)
    p.add_argument("--backend", choices=["heuristic", "ollama_embedding"], default="heuristic")
    p.add_argument("--model-id", default="bge-m3:latest")
    p = sub.add_parser("graph-reasoning")
    p.add_argument("--text", required=True)
    p.add_argument("--history-file")
    p.add_argument("--out")
    p = sub.add_parser("run-graph-reasoning-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "graph_reasoning_v4_cases.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("adaptive-render")
    p.add_argument("--text", required=True)
    p.add_argument("--history-file")
    p.add_argument("--profile", default="default")
    p.add_argument("--profile-file")
    p.add_argument("--out")
    p = sub.add_parser("run-renderer-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "renderer_v5_dev_cases.jsonl"))
    p.add_argument("--out", required=True)
    p.add_argument("--split", default="dev")
    p = sub.add_parser("run-profile-validation-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "renderer_v5_profile_adversarial.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-structured-assurance-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "structured_assurance_benchmark_v1.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-candidate-assurance-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "candidate_assurance_benchmark_v1.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-acceptance-challenge-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "acceptance_challenge_benchmark_v1.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-public-readiness-evidence")
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-reference-performance")
    p.add_argument("--out", required=True)
    p.add_argument("--repeats", type=int, default=20)
    p = sub.add_parser("run-quality-discovery-campaign")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "quality_discovery_v1.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-quality-discovery-aggregate")
    p.add_argument("--out", required=True)
    p = sub.add_parser("run-grading-assurance-benchmark")
    p.add_argument("--cases", default=str(PACKAGE_ROOT / "fixtures" / "grading_assurance_benchmark_v1.jsonl"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("unknown-language")
    p.add_argument("--text", required=True)
    p.add_argument("--language-hint", default="auto")
    p.add_argument("--session-file")
    p.add_argument("--session-out")
    p.add_argument("--out")
    p = sub.add_parser("reduce-acceptance")
    p.add_argument("run_dir")
    p = sub.add_parser("scan-redlines")
    p.add_argument("target")
    p = sub.add_parser("summarize-release")
    p.add_argument("run_dir")
    args = parser.parse_args(argv)
    if args.cmd == "validate-schema":
        return validate_schema(args.target)
    if args.cmd == "run-smoke":
        return run_smoke(args.out)
    if args.cmd == "run-empirical":
        return run_empirical(args.fixtures, args.out)
    if args.cmd == "generate-fixture-bank":
        return generate_fixture_bank_cmd(args.out, args.per_family)
    if args.cmd == "run-baseline-comparison":
        return baseline_comparison_cmd(args.fixtures, args.out)
    if args.cmd == "run-small-model-adapter":
        return small_model_adapter_cmd(args.fixtures, args.out, args.mode, args.model_id)
    if args.cmd == "run-measurement-series":
        return measurement_series_cmd(args.fixtures, args.out, args.repeats)
    if args.cmd == "answer-limited-domain":
        return answer_limited_domain_cmd(args.fixtures, args.query, args.out)
    if args.cmd == "run-hardware-benchmark-validation":
        return hardware_benchmark_validation_cmd(args.fixtures, args.out, args.repeats)
    if args.cmd == "run-natural-language-benchmark":
        return natural_language_benchmark_cmd(args.fixtures, args.benchmark, args.out)
    if args.cmd == "run-rule-grounding-benchmark":
        return rule_grounding_benchmark_cmd(args.cases, args.out)
    if args.cmd == "run-rule-composition-benchmark":
        return rule_composition_benchmark_cmd(args.cases, args.out)
    if args.cmd == "run-policy-pack-lifecycle-benchmark":
        return policy_pack_lifecycle_benchmark_cmd(args.cases, args.out)
    if args.cmd == "seeded-dialogue":
        return seeded_dialogue_cmd(args.text, args.out)
    if args.cmd == "run-seeded-dialogue-benchmark":
        return seeded_dialogue_benchmark_cmd(args.cases, args.out)
    if args.cmd == "chunked-dialogue":
        return chunked_dialogue_cmd(args.text, args.out)
    if args.cmd == "run-chunked-dialogue-benchmark":
        return chunked_dialogue_benchmark_cmd(args.cases, args.out)
    if args.cmd == "history-chunked-dialogue":
        return history_chunked_dialogue_cmd(args.text, args.history_file, args.out)
    if args.cmd == "run-history-chunked-dialogue-benchmark":
        return history_chunked_dialogue_benchmark_cmd(args.cases, args.out)
    if args.cmd == "topic-continuity-dialogue":
        return topic_continuity_dialogue_cmd(args.text, args.history_file, args.out)
    if args.cmd == "run-topic-continuity-benchmark":
        return topic_continuity_benchmark_cmd(args.cases, args.out)
    if args.cmd == "coding-task":
        return coding_task_cmd(args.prompt, args.history_file, args.out)
    if args.cmd == "run-coding-task-benchmark":
        return coding_task_benchmark_cmd(args.cases, args.out)
    if args.cmd == "semantic-chunk":
        return semantic_chunk_cmd(args.text, args.language_hint, args.out)
    if args.cmd == "run-semantic-chunk-benchmark":
        return semantic_chunk_benchmark_cmd(args.cases, args.out)
    if args.cmd == "run-sparse-attention-benchmark":
        return sparse_attention_benchmark_cmd(args.cases, args.out)
    if args.cmd == "neural-candidate":
        return neural_candidate_cmd(args.text, args.backend, args.model_id, args.out)
    if args.cmd == "run-neural-candidate-benchmark":
        return neural_candidate_benchmark_cmd(args.cases, args.out, args.backend, args.model_id)
    if args.cmd == "graph-reasoning":
        return graph_reasoning_cmd(args.text, args.history_file, args.out)
    if args.cmd == "run-graph-reasoning-benchmark":
        return graph_reasoning_benchmark_cmd(args.cases, args.out)
    if args.cmd == "adaptive-render":
        return adaptive_render_cmd(args.text, args.history_file, args.profile, args.profile_file, args.out)
    if args.cmd == "run-renderer-benchmark":
        return renderer_benchmark_cmd(args.cases, args.out, args.split)
    if args.cmd == "run-profile-validation-benchmark":
        return profile_validation_benchmark_cmd(args.cases, args.out)
    if args.cmd == "run-structured-assurance-benchmark":
        return structured_assurance_benchmark_cmd(args.cases, args.out)
    if args.cmd == "run-candidate-assurance-benchmark":
        return candidate_assurance_benchmark_cmd(args.cases, args.out)
    if args.cmd == "run-acceptance-challenge-benchmark":
        return acceptance_challenge_benchmark_cmd(args.cases, args.out)
    if args.cmd == "run-public-readiness-evidence":
        return public_readiness_evidence_cmd(args.out)
    if args.cmd == "run-reference-performance":
        return reference_performance_cmd(args.out, args.repeats)
    if args.cmd == "run-quality-discovery-campaign":
        return quality_discovery_campaign_cmd(args.cases, args.out)
    if args.cmd == "run-quality-discovery-aggregate":
        return quality_discovery_aggregate_cmd(args.out)
    if args.cmd == "run-grading-assurance-benchmark":
        return grading_assurance_benchmark_cmd(args.cases, args.out)
    if args.cmd == "unknown-language":
        return unknown_language_cmd(args.text, args.language_hint, args.session_file, args.session_out, args.out)
    if args.cmd == "reduce-acceptance":
        return reduce_acceptance_cmd(args.run_dir)
    if args.cmd == "scan-redlines":
        return scan_redlines(args.target)
    if args.cmd == "summarize-release":
        return summarize_release(args.run_dir)
    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
