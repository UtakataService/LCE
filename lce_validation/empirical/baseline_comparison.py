from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from ..schema_tools import write_jsonl
from .engine import fixture_evidence_rows, load_jsonl, run_empirical_slice


def run_baseline_comparison(fixtures_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fixtures = load_jsonl(fixtures_path)
    structural_summary = run_empirical_slice(fixtures_path, out / "structural")
    comparison_rows = []
    for fixture in fixtures:
        b3 = run_b3_bm25_like(fixture, fixture_evidence_rows(fixture), out.name)
        comparison_rows.append({
            "comparison_id": f"cmp-{fixture['fixture_id']}",
            "fixture_id": fixture["fixture_id"],
            "expected_outcome": fixture.get("expected_outcome"),
            "b3_result": b3["result_ref"],
            "b3_score": b3["score"],
            "b3_failure_profile": b3["failure_profile"],
            "claim_scope": "baseline_separability_only",
        })
    write_jsonl(out / "baseline_b3_runs.jsonl", [row["b3_row"] for row in _with_b3_rows(fixtures, out.name)])
    write_jsonl(out / "comparison_rows.jsonl", comparison_rows)
    summary = {
        "ok": True,
        "run_id": out.name,
        "fixture_count": len(fixtures),
        "b3_rows": len(comparison_rows),
        "structural_summary_ref": str(out / "structural" / "empirical_summary.json"),
        "structural_decision_counts": structural_summary["decision_counts"],
        "b3_result_counts": _count(row["b3_result"] for row in comparison_rows),
        "claim": "baseline_separability_only",
    }
    (out / "baseline_comparison_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def run_b3_bm25_like(fixture: dict[str, Any], evidence_rows: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    query_tokens = _tokens(fixture.get("question", ""))
    docs = [_tokens(row.get("text", "")) for row in evidence_rows]
    best_score = 0.0
    for doc in docs:
        best_score = max(best_score, _bm25_like(query_tokens, doc, docs))
    if best_score >= 2.5:
        result = "candidate_evidence_found"
    elif best_score > 0:
        result = "weak_overlap"
    else:
        result = "UNKNOWN_MODEL_GAP"
    return {
        "baseline_run_id": f"baseline-{run_id}-{fixture['fixture_id']}-B3",
        "baseline_id": "DATA-B3",
        "fixture_id": fixture["fixture_id"],
        "candidate_id": fixture["candidate_ids"][0],
        "run_id": run_id,
        "lane_label": "WIN_CPU_FIRST",
        "result_ref": result,
        "score": round(best_score, 6),
        "failure_profile": "bm25_like_lexical_only; no entailment or contradiction semantics",
        "resource_snapshot_ref": "comparison-not-measured",
        "replay_manifest_ref": "comparison-run",
        "adjudication_status": "baseline_only",
        "block_condition_triggered": result != fixture.get("expected_outcome"),
    }


def _with_b3_rows(fixtures: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    return [{"b3_row": run_b3_bm25_like(fixture, fixture_evidence_rows(fixture), run_id)} for fixture in fixtures]


def _tokens(text: str) -> list[str]:
    return [tok for tok in re.findall(r"[A-Za-z0-9_]+", text.lower()) if len(tok) > 1]


def _bm25_like(query: list[str], doc: list[str], corpus: list[list[str]]) -> float:
    if not query or not doc:
        return 0.0
    avgdl = sum(len(row) for row in corpus) / max(len(corpus), 1)
    k1 = 1.2
    b = 0.75
    score = 0.0
    for term in set(query):
        freq = doc.count(term)
        if not freq:
            continue
        containing = sum(1 for row in corpus if term in row)
        idf = math.log(1 + (len(corpus) - containing + 0.5) / (containing + 0.5))
        denom = freq + k1 * (1 - b + b * len(doc) / max(avgdl, 1))
        score += idf * (freq * (k1 + 1)) / denom
    return score


def _count(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts
