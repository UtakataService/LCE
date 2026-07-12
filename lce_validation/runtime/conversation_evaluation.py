"""Independent-evaluation contracts for ConversationOrchestrator Phase 2.

This is intentionally a small evaluator.  It proves custody and transition
properties for supplied fixtures; it does not claim a blind or sealed score
until independent fixture banks are actually supplied.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .conversation_contract import ContractError, canonical_json, empty_conversation_state, state_hash, validate_replay_fixture
from .conversation_reducer import reduce_turn, replay_fixture


ACTOR_ROLES = {"Builder", "Splitter", "Implementer", "Evaluator", "Adjudicator", "ReleaseApprover"}
SPLITS = {"exposed", "interaction_blind", "sealed"}
REQUIRED_MANIFEST_FIELDS = {
    "case_id", "semantic_group_id", "scenario_parent_id", "lineage_id",
    "language", "language_role", "family", "turn_count", "split",
    "generation_method", "author_role", "fixture_hash",
}
AXIS_DELTA_CLASSES = {"APPEND_HYPOTHESIS", "RETRACT_TENTATIVE", "EPHEMERAL_FORGET", "PRIVACY_FLAG", "TOPIC_OPERATION", "REVISION_ONLY"}
AXIS_EVIDENCE_REQUIREMENTS = {"required", "none"}


def fixture_hash(fixture: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(dict(fixture)).encode("utf-8")).hexdigest()


def validate_split_manifest(rows: list[Mapping[str, Any]]) -> None:
    """Reject cross-split semantic siblings before any evaluation is trusted."""
    if not isinstance(rows, list) or not rows:
        raise ContractError("EMPTY_SPLIT_MANIFEST")
    groups: dict[str, str] = {}
    case_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or REQUIRED_MANIFEST_FIELDS - set(row):
            raise ContractError("INVALID_MANIFEST_ROW")
        if row["split"] not in SPLITS or row["author_role"] not in ACTOR_ROLES:
            raise ContractError("INVALID_MANIFEST_ENUM")
        if not isinstance(row["case_id"], str) or row["case_id"] in case_ids:
            raise ContractError("DUPLICATE_MANIFEST_CASE")
        case_ids.add(row["case_id"])
        group_id = row["semantic_group_id"]
        prior = groups.setdefault(group_id, row["split"])
        if prior != row["split"]:
            raise ContractError("CROSS_SPLIT_SEMANTIC_GROUP")


def make_ledger_event(*, event_id: str, timestamp_utc: str, actor_role: str, action: str, artifact_type: str, artifact_id: str, artifact_hash: str, semantic_group_ids: list[str], split: str, parent_event_hash: str | None, build_hash: str, config_hash: str, reason_code: str, notes_redacted: str = "") -> dict[str, Any]:
    if actor_role not in ACTOR_ROLES or split not in SPLITS:
        raise ContractError("INVALID_LEDGER_ENUM")
    event = {
        "event_id": event_id,
        "timestamp_utc": timestamp_utc,
        "actor_role": actor_role,
        "action": action,
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "artifact_hash": artifact_hash,
        "semantic_group_ids_hash": _group_hash(semantic_group_ids),
        "split": split,
        "parent_event_hash": parent_event_hash,
        "build_hash": build_hash,
        "config_hash": config_hash,
        "reason_code": reason_code,
        "notes_redacted": notes_redacted,
    }
    event["event_hash"] = _event_hash(event)
    return event


def verify_custody_ledger(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate hash continuity and declare compromised blind/sealed lineages."""
    violations: list[str] = []
    parent: str | None = None
    compromised: set[str] = set()
    for index, event in enumerate(events):
        required = {"event_hash", "parent_event_hash", "actor_role", "action", "split", "semantic_group_ids_hash"}
        if not isinstance(event, Mapping) or required - set(event):
            violations.append(f"ledger:{index}:INVALID_EVENT")
            continue
        payload = dict(event)
        stored_hash = payload.pop("event_hash")
        if stored_hash != _event_hash(payload):
            violations.append(f"ledger:{index}:HASH_MISMATCH")
        if event["parent_event_hash"] != parent:
            violations.append(f"ledger:{index}:PARENT_MISMATCH")
        if event["actor_role"] == "Implementer" and event["action"] in {"view", "failure_analysis"} and event["split"] in {"interaction_blind", "sealed"}:
            compromised.add(str(event["semantic_group_ids_hash"]))
        parent = str(stored_hash)
    return {"valid": not violations and not compromised, "violations": violations, "compromised_group_hashes": sorted(compromised)}


def append_ledger_event(path: str | Path, event: Mapping[str, Any]) -> None:
    """Append only after validating the existing chain and new parent link."""
    target = Path(path)
    existing = read_ledger(target)
    check = verify_custody_ledger(existing)
    if not check["valid"]:
        raise ContractError("EXISTING_LEDGER_INVALID")
    expected_parent = existing[-1]["event_hash"] if existing else None
    if event.get("parent_event_hash") != expected_parent:
        raise ContractError("LEDGER_PARENT_MISMATCH")
    if verify_custody_ledger(existing + [event])["violations"]:
        raise ContractError("INVALID_LEDGER_EVENT")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(dict(event)) + "\n")


def read_ledger(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate_fixture_case(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Score the exposed contract, replay chain, and no-raw-input invariant."""
    validate_replay_fixture(fixture)
    replay = replay_fixture(fixture)
    records = replay["result"]["records"]
    violations: list[str] = []
    prior_hash = state_hash(empty_conversation_state(session_id="fixture:" + str(fixture["case_id"])))
    for index, record in enumerate(records, start=1):
        if record["revision"] != index:
            violations.append(f"I-01:REVISION:{index}")
        if record["parent_hash"] != prior_hash:
            violations.append(f"I-01:PARENT_HASH:{index}")
        if record["response_step"] == "answer" and record["precedence"] == "knowledge":
            violations.append(f"I-07:UNGROUNDED_ANSWER:{index}")
        prior_hash = record["state_hash"]
    serialized = canonical_json(replay["result"])
    if any(turn["text"] in serialized for turn in fixture["turns"]):
        violations.append("TRACE_CONTAINS_RAW_INPUT")
    if not replay["passed"]:
        violations.append("EXPECTED_PLAN_OR_FORBIDDEN_MISMATCH")
    return {
        "case_id": fixture["case_id"],
        "passed": not violations,
        "violations": violations,
        "terminal_precedence": records[-1]["precedence"],
        "terminal_step": records[-1]["response_step"],
        "state_hash": replay["result"]["state_hash"],
    }


def evaluate_exposed_bank(fixtures: list[Mapping[str, Any]]) -> dict[str, Any]:
    results = [evaluate_fixture_case(fixture) for fixture in fixtures]
    passed = sum(item["passed"] for item in results)
    return {
        "scope": "exposed_only",
        "case_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "p0_violations": [violation for item in results for violation in item["violations"] if violation.startswith(("I-02", "I-03", "I-04", "I-06", "I-07", "I-08", "I-11"))],
        "results": results,
        "claim_boundary": "No blind, sealed, or general-dialogue capability claim is supported by this exposed bank.",
    }


def validate_axis_fixture(fixture: Mapping[str, Any]) -> None:
    validate_replay_fixture(fixture)
    gold = fixture.get("gold")
    required = {"precedence", "response_step", "forbidden_set", "state_delta_class", "evidence_requirement"}
    if not isinstance(gold, Mapping) or required - set(gold):
        raise ContractError("INVALID_AXIS_GOLD")
    if not isinstance(gold["forbidden_set"], list) or not all(isinstance(item, str) for item in gold["forbidden_set"]):
        raise ContractError("INVALID_AXIS_FORBIDDEN")
    if gold["state_delta_class"] not in AXIS_DELTA_CLASSES or gold["evidence_requirement"] not in AXIS_EVIDENCE_REQUIREMENTS:
        raise ContractError("INVALID_AXIS_GOLD")


def evaluate_axis_case(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate P/R/F/Delta/E separately for a new exposed lineage."""
    validate_axis_fixture(fixture)
    state = empty_conversation_state(session_id="axis:" + str(fixture["case_id"]))
    terminal: dict[str, Any] | None = None
    before_terminal: dict[str, Any] | None = None
    for turn in fixture["turns"]:
        before_terminal = state
        terminal = reduce_turn(state, turn["text"])
        state = terminal["state"]
    assert terminal is not None and before_terminal is not None
    actual = {
        "precedence": terminal["precedence"],
        "response_step": terminal["plan"]["response_steps"][0]["kind"],
        "forbidden_set": sorted(terminal["plan"]["response_steps"][0]["forbidden"]),
        "state_delta_class": _state_delta_class(before_terminal, state),
        "evidence_requirement": _evidence_requirement(terminal["plan"]),
    }
    gold = fixture["gold"]
    matches = {
        "precedence": actual["precedence"] == gold["precedence"],
        "response_step": actual["response_step"] == gold["response_step"],
        "forbidden_policy": actual["forbidden_set"] == sorted(gold["forbidden_set"]),
        "state_delta": actual["state_delta_class"] == gold["state_delta_class"],
        "evidence": actual["evidence_requirement"] == gold["evidence_requirement"],
    }
    return {"case_id": fixture["case_id"], "matches": matches, "actual": actual, "gold": dict(gold), "passed": all(matches.values())}


def evaluate_axis_bank(fixtures: list[Mapping[str, Any]]) -> dict[str, Any]:
    results = [evaluate_axis_case(fixture) for fixture in fixtures]
    axes = ("precedence", "response_step", "forbidden_policy", "state_delta", "evidence")
    return {
        "scope": "exposed_axis_lineage",
        "case_count": len(results),
        "overall_passed": sum(item["passed"] for item in results),
        "overall_failed": sum(not item["passed"] for item in results),
        "axes": {axis: {"matched": sum(item["matches"][axis] for item in results), "mismatched": sum(not item["matches"][axis] for item in results)} for axis in axes},
        "results": results,
        "claim_boundary": "This is an exposed contract-diagnosis bank, not a blind or sealed capability result.",
    }


def run_interaction_blind_bank(*, fixtures_path: str | Path, manifest_path: str | Path, custody_path: str | Path, timestamp_utc: str, build_hash: str, config_hash: str) -> dict[str, Any]:
    """Evaluate a blind bank without returning fixture text or human-readable IDs.

    The caller must have received a split ledger from a distinct Splitter role.
    This function adds only an Evaluator run event after the bank has passed
    manifest and custody checks.
    """
    fixtures = _read_jsonl(fixtures_path)
    manifest = _read_jsonl(manifest_path)
    validate_split_manifest(manifest)
    if any(row["split"] != "interaction_blind" for row in manifest):
        raise ContractError("NON_BLIND_MANIFEST")
    indexed = {str(row["case_id"]): row for row in fixtures}
    if set(indexed) != {str(row["case_id"]) for row in manifest}:
        raise ContractError("MANIFEST_FIXTURE_SET_MISMATCH")
    for row in manifest:
        if fixture_hash(indexed[str(row["case_id"])]) != row["fixture_hash"]:
            raise ContractError("BLIND_FIXTURE_HASH_MISMATCH")

    existing = read_ledger(custody_path)
    audit = verify_custody_ledger(existing)
    if not audit["valid"]:
        raise ContractError("BLIND_CUSTODY_INVALID")
    if not any(event.get("actor_role") == "Splitter" and event.get("action") == "split" and event.get("split") == "interaction_blind" for event in existing):
        raise ContractError("MISSING_BLIND_SPLIT_EVENT")

    report = evaluate_exposed_bank(fixtures)
    event = make_ledger_event(
        event_id="eval:" + hashlib.sha256((str(manifest_path) + build_hash + config_hash).encode("utf-8")).hexdigest()[:16],
        timestamp_utc=timestamp_utc,
        actor_role="Evaluator",
        action="run",
        artifact_type="evaluation_report",
        artifact_id="blind:" + hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()[:16],
        artifact_hash="sha256:" + hashlib.sha256(canonical_json(report).encode("utf-8")).hexdigest(),
        semantic_group_ids=sorted({str(row["semantic_group_id"]) for row in manifest}),
        split="interaction_blind",
        parent_event_hash=existing[-1]["event_hash"],
        build_hash=build_hash,
        config_hash=config_hash,
        reason_code="INTERACTION_BLIND_RUN",
        notes_redacted="aggregate-only runner; fixture text intentionally omitted",
    )
    append_ledger_event(custody_path, event)
    return {
        "scope": "interaction_blind",
        "custody_valid": True,
        "case_count": report["case_count"],
        "passed": report["passed"],
        "failed": report["failed"],
        "p0_violations": report["p0_violations"],
        "case_digests": [{
            "case_hash": "sha256:" + hashlib.sha256(item["case_id"].encode("utf-8")).hexdigest(),
            "passed": item["passed"],
            "violation_codes": item["violations"],
        } for item in report["results"]],
        "claim_boundary": "This same-machine role-separated run is not a third-party independent evaluation or a sealed release result.",
    }


def _event_hash(event_without_hash: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(dict(event_without_hash)).encode("utf-8")).hexdigest()


def _group_hash(group_ids: list[str]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(sorted(group_ids)).encode("utf-8")).hexdigest()


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        raise ContractError("MISSING_EVALUATION_ARTIFACT")
    try:
        return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise ContractError("INVALID_EVALUATION_JSONL") from exc


def _state_delta_class(before: Mapping[str, Any], after: Mapping[str, Any]) -> str:
    if "persistent_deletion_not_claimed" in after["safety_flags"]:
        return "EPHEMERAL_FORGET"
    if "privacy_sensitive_input" in after["safety_flags"]:
        return "PRIVACY_FLAG"
    if any(item["status"] == "RETRACTED" for item in after["interpretations"]) and not any(item["status"] == "RETRACTED" for item in before["interpretations"]):
        return "RETRACT_TENTATIVE"
    if after["topic_stack"] != before["topic_stack"]:
        return "TOPIC_OPERATION"
    if len(after["interpretations"]) > len(before["interpretations"]):
        return "APPEND_HYPOTHESIS"
    return "REVISION_ONLY"


def _evidence_requirement(plan: Mapping[str, Any]) -> str:
    """Only interpretations selected into this plan require decision evidence."""
    selected = plan.get("selected_interpretation_ids", [])
    return "required" if selected else "none"
