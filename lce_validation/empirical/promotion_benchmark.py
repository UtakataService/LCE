"""Deterministic benchmark for the Knowledge Unit promotion gate.

The benchmark deliberately separates probabilistic calibration from release
gates.  A good average score can never hide a false promotion, policy bypass,
or retrieval of non-active knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence


ACTIVE_RETRIEVAL_STATES = frozenset({"ACTIVE_L1", "ACTIVE_L2", "ACTIVE_L3"})


@dataclass(frozen=True)
class CalibrationPoint:
    confidence: float
    correct: bool
    decision: str = "PASS"

    def __post_init__(self) -> None:
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be finite and within [0, 1]")
        if self.decision not in {"PASS", "FAIL", "UNKNOWN"}:
            raise ValueError("decision must be PASS, FAIL, or UNKNOWN")


def calibration_metrics(points: Iterable[CalibrationPoint], *, bins: int = 10) -> dict[str, Any]:
    """Return bounded calibration metrics without treating abstention as success."""
    rows = tuple(points)
    if not rows:
        raise ValueError("at least one calibration point is required")
    if bins < 1:
        raise ValueError("bins must be positive")
    brier = sum((row.confidence - float(row.correct)) ** 2 for row in rows) / len(rows)
    ece = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        bucket = [row for row in rows if low <= row.confidence < high or (index == bins - 1 and row.confidence == 1.0)]
        if bucket:
            accuracy = sum(row.correct for row in bucket) / len(bucket)
            confidence = sum(row.confidence for row in bucket) / len(bucket)
            ece += len(bucket) / len(rows) * abs(accuracy - confidence)
    decided = [row for row in rows if row.decision != "UNKNOWN"]
    false_promotions = sum(row.decision == "PASS" and not row.correct for row in rows)
    return {
        "count": len(rows),
        "brier": round(brier, 6),
        "ece": round(ece, 6),
        "coverage": round(len(decided) / len(rows), 6),
        "false_promotions": false_promotions,
        "fprom": round(false_promotions / len(rows), 6),
    }


def evaluate_language_regression(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    counts: dict[str, int] = {key: 0 for key in ("en", "ja", "vi", "unknown")}
    for index, row in enumerate(rows):
        expected = str(row["expected_language"])
        actual = str(row["actual_language"])
        counts.setdefault(expected, 0)
        counts[expected] += 1
        if actual != expected:
            failures.append(f"language[{index}]:expected={expected}:actual={actual}")
        if expected == "unknown" and bool(row.get("promoted", False)):
            failures.append(f"language[{index}]:unknown_promoted")
        if bool(row.get("executable", False)) and expected in {"vi", "unknown"} and not row.get("intent_verified", False):
            failures.append(f"language[{index}]:unverified_intent_executable")
    return _suite("language", counts, failures)


def evaluate_policy_regression(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    count = 0
    for index, row in enumerate(rows):
        count += 1
        required = str(row.get("expected", "DENY"))
        actual = str(row.get("actual", "UNKNOWN"))
        if actual != required:
            failures.append(f"policy[{index}]:expected={required}:actual={actual}")
        if row.get("risk") == "high" and actual == "ALLOW" and not row.get("approval_present", False):
            failures.append(f"policy[{index}]:high_risk_bypass")
    return _suite("policy", {"total": count}, failures)


def evaluate_retrieval_regression(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    count = 0
    for index, row in enumerate(rows):
        count += 1
        state = str(row.get("status", "UNKNOWN"))
        if state not in ACTIVE_RETRIEVAL_STATES:
            failures.append(f"retrieval[{index}]:non_active={state}")
        if row.get("tenant_id") != row.get("query_tenant_id"):
            failures.append(f"retrieval[{index}]:tenant_leak")
        if row.get("scope_match") is not True:
            failures.append(f"retrieval[{index}]:scope_leak")
        if row.get("language_match") is not True:
            failures.append(f"retrieval[{index}]:language_leak")
    return _suite("retrieval", {"total": count}, failures)


def run_promotion_benchmark(
    *,
    calibration: Sequence[CalibrationPoint | Mapping[str, Any]],
    languages: Sequence[Mapping[str, Any]],
    policies: Sequence[Mapping[str, Any]],
    retrieval: Sequence[Mapping[str, Any]],
    max_brier: float = 0.20,
    max_ece: float = 0.15,
) -> dict[str, Any]:
    points = [row if isinstance(row, CalibrationPoint) else CalibrationPoint(**row) for row in calibration]
    metrics = calibration_metrics(points)
    suites = {
        "language": evaluate_language_regression(languages),
        "policy": evaluate_policy_regression(policies),
        "retrieval": evaluate_retrieval_regression(retrieval),
    }
    calibration_pass = (
        metrics["false_promotions"] == 0
        and metrics["brier"] <= max_brier
        and metrics["ece"] <= max_ece
    )
    blockers = []
    if not calibration_pass:
        blockers.append("calibration_gate_failed")
    blockers.extend(f"{name}_regression_failed" for name, suite in suites.items() if not suite["passed"])
    return {
        "schema_version": "promotion_benchmark_v1",
        "passed": not blockers,
        "release_decision": "GO" if not blockers else "NO_GO",
        "calibration": {**metrics, "passed": calibration_pass, "thresholds": {"brier": max_brier, "ece": max_ece, "false_promotions": 0}},
        "suites": suites,
        "blockers": blockers,
    }


def reference_fixture() -> dict[str, Any]:
    """Small deterministic smoke set; release runs should provide frozen fixtures."""
    return run_promotion_benchmark(
        calibration=[
            {"confidence": 0.95, "correct": True, "decision": "PASS"},
            {"confidence": 0.10, "correct": False, "decision": "FAIL"},
            {"confidence": 0.10, "correct": False, "decision": "UNKNOWN"},
            {"confidence": 0.85, "correct": True, "decision": "PASS"},
        ],
        languages=[
            {"expected_language": "en", "actual_language": "en"},
            {"expected_language": "ja", "actual_language": "ja"},
            {"expected_language": "vi", "actual_language": "vi", "executable": False},
            {"expected_language": "unknown", "actual_language": "unknown", "promoted": False},
        ],
        policies=[
            {"risk": "high", "approval_present": False, "actual": "DENY", "expected": "DENY"},
            {"risk": "low", "actual": "ALLOW", "expected": "ALLOW"},
        ],
        retrieval=[
            {"status": "ACTIVE_L1", "tenant_id": "t1", "query_tenant_id": "t1", "scope_match": True, "language_match": True},
        ],
    )


def _suite(name: str, counts: Mapping[str, int], failures: list[str]) -> dict[str, Any]:
    return {"name": name, "passed": not failures, "counts": dict(counts), "failure_count": len(failures), "failures": failures}


__all__ = [
    "ACTIVE_RETRIEVAL_STATES", "CalibrationPoint", "calibration_metrics",
    "evaluate_language_regression", "evaluate_policy_regression",
    "evaluate_retrieval_regression", "reference_fixture", "run_promotion_benchmark",
]
