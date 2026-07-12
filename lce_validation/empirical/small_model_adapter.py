from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schema_tools import write_jsonl
from .engine import load_jsonl


def run_small_model_adapter(fixtures_path: str | Path, out_dir: str | Path, mode: str = "no_run", model_id: str = "unconfigured") -> dict[str, Any]:
    if mode not in {"no_run", "dry_run"}:
        raise ValueError("mode must be no_run or dry_run")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fixtures = load_jsonl(fixtures_path)
    rows = [_adapter_row(fixture, out.name, mode, model_id) for fixture in fixtures]
    write_jsonl(out / "data_b9_adapter_rows.jsonl", rows)
    summary = {
        "ok": True,
        "run_id": out.name,
        "mode": mode,
        "model_id": model_id,
        "fixture_count": len(fixtures),
        "adapter_rows": len(rows),
        "actual_model_calls": 0,
        "claim": "adapter_boundary_only",
        "blocked_claims": ["model_quality", "model_parity", "replacement", "benchmark_improvement"],
    }
    (out / "small_model_adapter_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _adapter_row(fixture: dict[str, Any], run_id: str, mode: str, model_id: str) -> dict[str, Any]:
    return {
        "baseline_run_id": f"baseline-{run_id}-{fixture['fixture_id']}-B9",
        "baseline_id": "DATA-B9",
        "fixture_id": fixture["fixture_id"],
        "candidate_id": fixture["candidate_ids"][0],
        "run_id": run_id,
        "lane_label": "WIN_CPU_FIRST",
        "result_ref": "NOT_RUN" if mode == "no_run" else "DRY_RUN_NOT_MODEL_OUTPUT",
        "failure_profile": "small_model_adapter_boundary_only; no actual model call",
        "resource_snapshot_ref": "adapter-boundary-not-measured",
        "replay_manifest_ref": "adapter-boundary",
        "adjudication_status": mode,
        "block_condition_triggered": True,
        "model_id": model_id,
        "actual_model_call": False,
        "prompt_ref": f"prompt-{fixture['fixture_id']}",
    }
