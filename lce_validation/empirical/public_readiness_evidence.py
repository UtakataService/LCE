"""Produce bounded public-readiness evidence from fixed assurance fixtures."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .acceptance_challenge_benchmark import run_acceptance_challenge_benchmark
from .candidate_assurance_benchmark import run_candidate_assurance_benchmark
from .grading_assurance_benchmark import run_grading_assurance_benchmark


def run_public_readiness_evidence(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    reports = {
        "candidate_assurance": run_candidate_assurance_benchmark(fixtures / "candidate_assurance_benchmark_v1.jsonl", out / "candidate_assurance"),
        "grading_assurance": run_grading_assurance_benchmark(fixtures / "grading_assurance_benchmark_v1.jsonl", out / "grading_assurance"),
        "acceptance_challenge": run_acceptance_challenge_benchmark(fixtures / "acceptance_challenge_benchmark_v1.jsonl", out / "acceptance_challenge"),
    }
    summary = {
        "ok": all(report["ok"] for report in reports.values()),
        "suite_count": len(reports),
        "reports": {name: {"case_count": report["case_count"], "ok": report["ok"]} for name, report in reports.items()},
        "claim": "closed_fixture_assurance_contracts_only",
        "not_claimed": ["general_llm_quality", "20b_equivalence", "semantic_truth", "production_safety", "third_party_pack_trust"],
    }
    (out / "public_readiness_evidence_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
