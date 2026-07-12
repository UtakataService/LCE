"""Reproducible CPU-only performance audit for Dialogue Completion v1."""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from lce_validation.runtime.dialogue_completion import respond_with_completion


REPEATS = 1000


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percentile_value * len(ordered) + 0.999999999) // 1) - 1))
    return ordered[index]


def pending_history(slot: str, *, options: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    state = {
        "revision": 1,
        "goal": "compare",
        "status": "PENDING",
        "options": list(options),
        "priority_axis": None,
        "deletion_target": None,
        "deletion_scope": None,
        "schema_fields": [],
        "pending_slot": slot,
        "attempts": 0,
    }
    return [{"speaker": "assistant", "text": "確認します", "completion_state": state}]


def workload(index: int) -> tuple[str, list[dict[str, Any]]]:
    variant = index % 4
    if variant == 0:
        return "速度", pending_history("priority_axis", options=("MySQL", "JSON"))
    if variant == 1:
        return "なんとなく", pending_history("priority_axis", options=("MySQL", "JSON"))
    if variant == 2:
        return "MySQLとJSONを比較して", []
    return "LCEとは何ですか", []


def run_series(name: str, repeats: int, *, warmup: int) -> dict[str, Any]:
    for index in range(warmup):
        text, history = workload(index)
        respond_with_completion(text, history)

    wall_ms: list[float] = []
    internal_ms: list[float] = []
    response_chars: list[int] = []
    hashes: list[str] = []
    start_series = time.perf_counter_ns()
    start_cpu = time.process_time_ns()
    for index in range(repeats):
        text, history = workload(index)
        started = time.perf_counter_ns()
        result = respond_with_completion(text, history)
        wall_ms.append((time.perf_counter_ns() - started) / 1e6)
        internal_ms.append(float(result["latency_ms"]))
        response_chars.append(len(result["response"]))
        hashes.append(_stable_result_hash(result))
    cpu_s = (time.process_time_ns() - start_cpu) / 1e9
    wall_s = (time.perf_counter_ns() - start_series) / 1e9
    total_chars = sum(response_chars)
    return {
        "name": name,
        "repeats": repeats,
        "warmup": warmup,
        "wall_ms": summarize(wall_ms),
        "internal_ms": summarize(internal_ms),
        "wall_seconds": wall_s,
        "cpu_seconds": cpu_s,
        "turns_per_second": repeats / wall_s,
        "response_chars": {
            "total": total_chars,
            "mean_per_turn": statistics.fmean(response_chars),
            "chars_per_second": total_chars / wall_s,
        },
        "unique_result_hashes": len(set(hashes)),
    }


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "max": max(values),
        "mean": statistics.fmean(values),
    }


def history_scaling(repeats: int = 300) -> list[dict[str, Any]]:
    rows = []
    for history_size in (0, 8, 64, 256, 1024):
        history = [{"speaker": "user", "text": "背景"} for _ in range(history_size)]
        values = []
        for _ in range(repeats):
            started = time.perf_counter_ns()
            respond_with_completion("LCEとは何ですか", history)
            values.append((time.perf_counter_ns() - started) / 1e6)
        rows.append({"history_items": history_size, "repeats": repeats, **summarize(values)})
    return rows


def _stable_result_hash(result: dict[str, Any]) -> str:
    import hashlib

    value = dict(result)
    value.pop("latency_ms", None)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    args = parser.parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats must be positive")

    report = {
        "schema_version": "dialogue_completion_performance.v1",
        "environment": {
            "platform": platform.platform(),
            "python": sys.version,
            "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
            "pid": os.getpid(),
        },
        "measurement_contract": {
            "clock": "time.perf_counter_ns",
            "cpu_clock": "time.process_time_ns",
            "percentile": "nearest-rank",
            "cold_definition": "first series after import, no warm-up; process import time excluded",
            "warm_definition": "same process after 100 unmeasured warm-up turns",
            "scope": "synchronous Python completion call; no HTTP, DB, network, or external model",
        },
        "cold": run_series("cold", args.repeats, warmup=0),
        "warm": run_series("warm", args.repeats, warmup=100),
        "history_scaling": history_scaling(),
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
