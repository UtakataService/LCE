from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..systems.hardware_profile import local_hardware_profile, raspberry_pi_boundary_profile
from .measurement_series import run_measurement_series


DEFAULT_THRESHOLDS = {
    "max_mean_duration_seconds": 0.5,
    "max_artifact_bytes_per_run": 1_000_000,
    "required_repeats": 3,
    "require_stable_decisions": True,
    "require_stable_acceptance": True,
}


def run_hardware_benchmark_validation(
    fixtures_path: str | Path,
    out_dir: str | Path,
    repeats: int = 3,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    active_thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    hardware = {
        "windows_lane": local_hardware_profile(),
        "raspberry_pi_lane": raspberry_pi_boundary_profile(),
    }
    measurement = run_measurement_series(fixtures_path, out / "measurement", repeats=repeats)
    checks = _evaluate(measurement, hardware, active_thresholds)
    accepted = [row["name"] for row in checks if row["status"] == "pass"]
    blocked = [row["name"] for row in checks if row["status"] != "pass"]
    summary = {
        "ok": not blocked,
        "run_id": out.name,
        "fixtures_path": str(fixtures_path),
        "thresholds": active_thresholds,
        "hardware_profile_ref": "hardware_profile.json",
        "measurement_summary_ref": "measurement/measurement_series_summary.json",
        "checks": checks,
        "accepted_checks": accepted,
        "blocked_checks": blocked,
        "claim": "hardware_benchmark_validation_only",
        "accepted_claims": _accepted_claims(checks),
        "blocked_claims": _blocked_claims(checks),
    }
    (out / "hardware_profile.json").write_text(json.dumps(hardware, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "validation_checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "hardware_benchmark_validation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _evaluate(measurement: dict[str, Any], hardware: dict[str, Any], thresholds: dict[str, Any]) -> list[dict[str, Any]]:
    duration_mean = measurement["duration_seconds"]["mean"]
    artifact_max = measurement["artifact_bytes"]["max"]
    checks = [
        _check(
            "windows_lane_profile_present",
            bool(hardware["windows_lane"].get("cpu_count_logical")),
            f"cpu_count_logical={hardware['windows_lane'].get('cpu_count_logical')}",
        ),
        _check(
            "measurement_repeats_met",
            measurement["repeats"] >= thresholds["required_repeats"],
            f"repeats={measurement['repeats']} required={thresholds['required_repeats']}",
        ),
        _check(
            "mean_duration_under_threshold",
            duration_mean <= thresholds["max_mean_duration_seconds"],
            f"mean={duration_mean} threshold={thresholds['max_mean_duration_seconds']}",
        ),
        _check(
            "artifact_footprint_under_threshold",
            artifact_max <= thresholds["max_artifact_bytes_per_run"],
            f"max={artifact_max} threshold={thresholds['max_artifact_bytes_per_run']}",
        ),
        _check(
            "stable_decision_counts",
            (not thresholds["require_stable_decisions"]) or measurement["stable_decision_counts"],
            f"stable={measurement['stable_decision_counts']}",
        ),
        _check(
            "stable_acceptance_counts",
            (not thresholds["require_stable_acceptance"]) or measurement["stable_acceptance_counts"],
            f"stable={measurement['stable_acceptance_counts']}",
        ),
        _check(
            "raspberry_pi_boundary_only",
            hardware["raspberry_pi_lane"]["status"] == "not_measured",
            "Pi lane remains a non-impacting boundary record",
        ),
    ]
    return checks


def _check(name: str, passed: bool, detail: str) -> dict[str, str]:
    return {"name": name, "status": "pass" if passed else "fail", "detail": detail}


def _accepted_claims(checks: list[dict[str, str]]) -> list[str]:
    names = {row["name"] for row in checks if row["status"] == "pass"}
    claims = ["windows_cpu_first_local_benchmark_lane"] if "windows_lane_profile_present" in names else []
    if {"measurement_repeats_met", "mean_duration_under_threshold", "stable_decision_counts", "stable_acceptance_counts"} <= names:
        claims.append("bounded_repeated_run_threshold_pass")
    return claims


def _blocked_claims(checks: list[dict[str, str]]) -> list[str]:
    blocked = ["production_readiness", "llm_quality_parity", "transformer_replacement"]
    if any(row["name"] == "raspberry_pi_boundary_only" and row["status"] == "pass" for row in checks):
        blocked.append("raspberry_pi_sufficiency")
    if any(row["status"] != "pass" for row in checks):
        blocked.append("benchmark_threshold_release")
    return blocked
