"""Cross-family quality discovery loop for bounded LCE capabilities.

The campaign records expected contract behavior, observed behavior, a proposed
failure owner, and a reinforcement target. It is not a general LLM benchmark.
"""
from __future__ import annotations

import json
import hashlib
import statistics
import time
from pathlib import Path
from typing import Any, Mapping

from .coding_task_runner import run_coding_task
from .engine import load_jsonl
from .topic_continuity_dialogue import respond_with_topic_continuity
from ..runtime.acceptance_challenge import challenge_accepted_result
from ..runtime.candidate_assurance import assess_candidate
from ..runtime.daily_dialogue import respond_daily_dialogue
from ..runtime.grading_assurance import audit_grading_records


def run_quality_discovery_campaign(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case in load_jsonl(cases_path):
        started = time.perf_counter()
        actual = _run_case(case)
        latency_ms = round((time.perf_counter() - started) * 1000, 6)
        expected = case["expected"]
        mismatches = [path for path, expected_value in expected.items() if _read_path(actual, path) != expected_value]
        mismatches.extend(_content_mismatches(actual, case))
        known_limit = bool(case.get("known_limit", False))
        status = "UNEXPECTED_FAILURE" if mismatches else "SAFE_LIMIT" if known_limit else "PASS"
        row = {
            "case_id": case["case_id"],
            "input_digest": "sha256:" + hashlib.sha256(json.dumps(case.get("payload", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "family": case["family"],
            "split": case.get("split", "development"),
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "expected": expected,
            "actual": {path: _read_path(actual, path) for path in expected},
            "expected_failure_hypothesis": {
                "failure_class": case.get("failure_class"),
                "owner": case.get("owner"),
                "reinforcement_target": case.get("reinforcement_target"),
            },
            "observed_failure_signature": {"mismatch_paths": mismatches, "actual_contract": {path: _read_path(actual, path) for path in expected}},
            "status": status,
            "mismatch_paths": mismatches,
            "failure_class": case.get("failure_class"),
            "owner": case.get("owner"),
            "reinforcement_target": case.get("reinforcement_target"),
            "priority": case.get("priority", 0),
            "known_limit": known_limit,
            "limit_metadata": case.get("limit_metadata"),
            "latency_ms": latency_ms,
        }
        rows.append(row)
    failures = [row for row in rows if row["status"] == "UNEXPECTED_FAILURE"]
    summary = {
        "ok": not failures,
        "run_id": out.name,
        "case_count": len(rows),
        "fixture_contracts_satisfied": not failures,
        "pass_count": sum(row["status"] == "PASS" for row in rows),
        "safe_limit_count": sum(row["status"] == "SAFE_LIMIT" for row in rows),
        "unexpected_failure_count": len(failures),
        "by_family": _summarize(rows, "family"),
        "by_split": _summarize(rows, "split"),
        "by_reinforcement_target": _summarize(failures, "reinforcement_target"),
        "priority_backlog": sorted((row for row in failures), key=lambda row: (-row["priority"], row["case_id"])),
        "case_rows_ref": "quality_discovery_rows.jsonl",
        "safe_limit_ledger": [
            {"case_id": row["case_id"], "family": row["family"], "reinforcement_target": row["reinforcement_target"], "limit_metadata": row["limit_metadata"]}
            for row in rows if row["status"] == "SAFE_LIMIT"
        ],
        "latency_ms": {
            "min": round(min(row["latency_ms"] for row in rows), 6),
            "mean": round(statistics.fmean(row["latency_ms"] for row in rows), 6),
            "max": round(max(row["latency_ms"] for row in rows), 6),
        },
        "claim": "bounded_cross_family_quality_discovery_only",
        "blocked_claims": ["general_dialogue_quality", "general_reasoning", "20b_equivalence", "model_safety", "production_readiness"],
    }
    (out / "quality_discovery_rows.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    (out / "quality_discovery_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _run_case(case: Mapping[str, Any]) -> Mapping[str, Any]:
    family = case.get("family")
    payload = case.get("payload", {})
    if family == "daily_dialogue":
        return respond_daily_dialogue(payload["text"], payload.get("history", []))
    if family == "topic_continuity":
        return respond_with_topic_continuity(payload["current_input"], payload.get("history", []))
    if family == "coding":
        return run_coding_task(payload["prompt"], payload.get("history", []))
    if family == "candidate_assurance":
        return assess_candidate(payload["candidate"], payload["policy"], payload["evidence_catalog"])
    if family == "grading_assurance":
        return audit_grading_records(payload["records"], payload["policy"], payload["evidence_catalog"])
    if family == "acceptance_challenge":
        return challenge_accepted_result(payload["result"], payload["policy"], payload["evidence_catalog"], payload.get("signals", []))
    raise ValueError("UNSUPPORTED_DISCOVERY_FAMILY")


def _read_path(value: Mapping[str, Any], path: str) -> Any:
    current: Any = value
    for segment in path.split("."):
        if isinstance(current, Mapping):
            if segment not in current:
                return None
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit() and int(segment) < len(current):
            current = current[int(segment)]
        else:
            return None
    return current


def _content_mismatches(actual: Mapping[str, Any], case: Mapping[str, Any]) -> list[str]:
    mismatches: list[str] = []
    for path, required_values in case.get("required_contains", {}).items():
        observed = _read_path(actual, path)
        for required in required_values:
            if not _contains(observed, required):
                mismatches.append(f"REQUIRED_CONTENT_MISSING:{path}:{required}")
    for path, forbidden_values in case.get("forbidden_contains", {}).items():
        observed = _read_path(actual, path)
        for forbidden in forbidden_values:
            if _contains(observed, forbidden):
                mismatches.append(f"FORBIDDEN_CONTENT_PRESENT:{path}:{forbidden}")
    return mismatches


def _contains(observed: Any, expected: Any) -> bool:
    if isinstance(observed, str) and isinstance(expected, str):
        return expected.casefold() in observed.casefold()
    if isinstance(observed, (list, tuple, set)):
        return expected in observed
    return False


def _summarize(rows: list[Mapping[str, Any]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        value = row.get(key) or "unclassified"
        result[str(value)] = result.get(str(value), 0) + 1
    return dict(sorted(result.items()))
