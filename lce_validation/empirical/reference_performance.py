"""Stdlib-only latency and allocation measurement for the Open Core reference path."""
from __future__ import annotations

import json
import platform
import statistics
import time
import tracemalloc
from pathlib import Path
from typing import Any

from ..open_core import OpenCoreSdk


def run_reference_performance(out_dir: str | Path, repeats: int = 20) -> dict[str, Any]:
    if not isinstance(repeats, int) or repeats < 1:
        raise ValueError("REPEATS_MUST_BE_POSITIVE")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    fixtures = root / "lce_validation" / "fixtures"
    durations_ms: list[float] = []
    tracemalloc.start()
    for _ in range(repeats):
        started = time.perf_counter()
        sdk = OpenCoreSdk(fixtures)
        locked = sdk.lock_profile(fixtures / "reference_profile_frame_v1.json")
        reference = locked["pack_refs"][0]
        report = sdk.run_language_conformance(reference["pack_id"], reference["pack_version"], reference["content_hash"], fixtures / "open_core_frame_parity_v1.jsonl")
        ledger = sdk.frame_shadow_difference_ledger(fixtures / "open_core_frame_parity_v1.jsonl")
        if report["failed"] or any(not row["equal"] for row in ledger):
            raise RuntimeError("REFERENCE_CONFORMANCE_FAILED")
        durations_ms.append((time.perf_counter() - started) * 1000)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ordered = sorted(durations_ms)
    summary = {
        "ok": True,
        "run_id": out.name,
        "repeats": repeats,
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine()},
        "reference_path": "profile_lock + 8-case_conformance + 8-case_shadow_ledger",
        "latency_ms": {
            "min": round(min(durations_ms), 6),
            "mean": round(statistics.fmean(durations_ms), 6),
            "p50": round(_percentile(ordered, 0.50), 6),
            "p95": round(_percentile(ordered, 0.95), 6),
            "max": round(max(durations_ms), 6),
        },
        "tracemalloc_peak_bytes": peak_bytes,
        "claim": "local_reference_open_core_path_only",
        "not_claimed": ["end_to_end_chat_latency", "external_llm_latency", "raspberry_pi_performance", "production_capacity", "general_model_quality"],
    }
    (out / "reference_performance_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _percentile(ordered: list[float], percentile: float) -> float:
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile + 0.999999)))
    return ordered[index]
