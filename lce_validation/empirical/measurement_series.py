from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any

from .engine import run_empirical_slice


def run_measurement_series(fixtures_path: str | Path, out_dir: str | Path, repeats: int = 3) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_rows: list[dict[str, Any]] = []
    for index in range(1, repeats + 1):
        run_dir = out / f"run_{index:02d}"
        started = time.perf_counter()
        summary = run_empirical_slice(fixtures_path, run_dir)
        elapsed = time.perf_counter() - started
        artifact_bytes = _directory_bytes(run_dir)
        run_rows.append({
            "series_index": index,
            "run_id": run_dir.name,
            "ok": summary["ok"],
            "fixture_count": summary["fixture_count"],
            "decision_counts": summary["decision_counts"],
            "acceptance_counts": summary["acceptance_counts"],
            "baseline_count": summary["baseline_count"],
            "duration_seconds": round(elapsed, 6),
            "engine_duration_seconds": summary["duration_seconds"],
            "artifact_bytes": artifact_bytes,
            "release_decision": summary["release_decision"],
        })

    duration_values = [row["duration_seconds"] for row in run_rows]
    byte_values = [row["artifact_bytes"] for row in run_rows]
    stable_decisions = len({json.dumps(row["decision_counts"], sort_keys=True) for row in run_rows}) == 1
    stable_acceptance = len({json.dumps(row["acceptance_counts"], sort_keys=True) for row in run_rows}) == 1
    summary = {
        "ok": all(row["ok"] for row in run_rows),
        "run_id": out.name,
        "fixtures_path": str(fixtures_path),
        "repeats": repeats,
        "duration_seconds": {
            "min": round(min(duration_values), 6),
            "max": round(max(duration_values), 6),
            "mean": round(statistics.fmean(duration_values), 6),
        },
        "artifact_bytes": {
            "min": min(byte_values),
            "max": max(byte_values),
            "mean": round(statistics.fmean(byte_values), 2),
        },
        "stable_decision_counts": stable_decisions,
        "stable_acceptance_counts": stable_acceptance,
        "claim": "local_measurement_only",
        "blocked_claims": [
            "cpu_pi_sufficiency",
            "production_readiness",
            "quality_parity",
            "transformer_replacement",
        ],
        "runs": run_rows,
    }
    _write_jsonl(out / "measurement_runs.jsonl", run_rows)
    (out / "measurement_series_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
