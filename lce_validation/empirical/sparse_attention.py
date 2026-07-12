from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .nl_normalization import normalize_tokens


ATTENTION_VERSION = "seed_graph_sparse_attention_v2"
HARD_EDGE_TYPES = {"policy_blocks", "requires_evidence", "supports_output", "repairs", "tests"}
DEFAULT_MAX_CANDIDATES = 128
DEFAULT_MAX_SELECTED = 32
DEFAULT_TOP_K_PER_TARGET = 4

ROLE_PRIOR = {
    ("policy", "assistant"): 1.0,
    ("verifier", "assistant"): 1.0,
    ("user", "assistant"): 0.85,
    ("user", "verifier"): 0.7,
    ("task", "assistant"): 0.75,
    ("user", "user"): 0.55,
}


def select_sparse_attention(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    max_selected: int = DEFAULT_MAX_SELECTED,
    top_k_per_target: int = DEFAULT_TOP_K_PER_TARGET,
) -> dict[str, Any]:
    node_by_id = {node["node_id"]: node for node in nodes}
    hard_input = [edge for edge in edges if edge["edge_type"] in HARD_EDGE_TYPES]
    soft_input = [edge for edge in edges if edge["edge_type"] not in HARD_EDGE_TYPES]
    soft_slots = max(0, max_candidates - len(hard_input))
    candidate_input = hard_input + sorted(soft_input, key=lambda edge: edge["edge_id"])[:soft_slots]
    candidates = [_score_edge(edge, node_by_id) for edge in candidate_input]
    candidate_truncated = len(candidate_input) < len(edges)
    candidate_hard_overflow = len(hard_input) > max_candidates

    hard = sorted(
        (row for row in candidates if row["hard"]),
        key=lambda row: row["candidate_id"],
    )
    hard_ids = {row["candidate_id"] for row in hard}
    soft = [row for row in candidates if row["candidate_id"] not in hard_ids]

    per_target: dict[str, list[dict[str, Any]]] = {}
    for row in soft:
        per_target.setdefault(row["to_node"], []).append(row)
    eligible: list[dict[str, Any]] = []
    for target in sorted(per_target):
        ranked = sorted(per_target[target], key=_rank_key)
        eligible.extend(ranked[:max(0, top_k_per_target)])

    soft_budget = max(0, max_selected - len(hard))
    selected_soft = sorted(eligible, key=_rank_key)[:soft_budget]
    selected_ids = hard_ids | {row["candidate_id"] for row in selected_soft}
    for row in candidates:
        row["selected"] = row["candidate_id"] in selected_ids
        row["selection_reason"] = (
            "hard_edge_preserved" if row["hard"]
            else "top_k_score" if row["selected"]
            else "pruned_by_budget_or_rank"
        )

    active_nodes = sorted({node_id for row in candidates if row["selected"] for node_id in (row["from_node"], row["to_node"])})
    selected_edge_ids = sorted(row["edge_id"] for row in candidates if row["selected"])
    hard_overflow = len(hard) > max_selected
    return {
        "ok": _hard_preserved(candidates) and _output_support_preserved(candidates, nodes),
        "attention_version": ATTENTION_VERSION,
        "candidate_count": len(candidates),
        "selected_count": len(selected_ids),
        "hard_count": len(hard),
        "soft_count": len(candidates) - len(hard),
        "candidate_truncated": candidate_truncated,
        "candidate_hard_overflow": candidate_hard_overflow,
        "hard_budget_overflow": hard_overflow,
        "limits": {
            "max_candidates": max_candidates,
            "max_selected": max_selected,
            "top_k_per_target": top_k_per_target,
        },
        "selected_candidate_ids": sorted(selected_ids),
        "selected_edge_ids": selected_edge_ids,
        "active_node_ids": active_nodes,
        "candidates": sorted(candidates, key=lambda row: row["candidate_id"]),
        "invariants": {
            "hard_edges_preserved": _hard_preserved(candidates),
            "output_support_preserved": _output_support_preserved(candidates, nodes),
            "deterministic_tie_break": "score_desc_then_candidate_id",
            "bounded_candidates": len(candidates) <= max(max_candidates, len(hard)),
        },
        "claim": "deterministic_bounded_sparse_edge_selector_only",
        "blocked_claims": [
            "learned_attention",
            "transformer_attention_equivalence",
            "global_semantic_optimality",
            "long_context_quality_parity",
            "llm_quality_parity",
        ],
    }


def run_sparse_attention_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    from .seed_graph import build_seed_graph

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in load_jsonl(cases_path):
        result = build_seed_graph(
            case["current_input"], case.get("history", []),
            task_hint=case.get("task_hint", "dialogue"),
            attention_limits=case.get("attention_limits"),
        )
        repeat = build_seed_graph(
            case["current_input"], case.get("history", []),
            task_hint=case.get("task_hint", "dialogue"),
            attention_limits=case.get("attention_limits"),
        )
        attention = result["sparse_attention"]
        checks = {
            "route": result["route"] == case["expected_route"],
            "attention_ok": attention["ok"],
            "hard_preserved": attention["invariants"]["hard_edges_preserved"],
            "support_preserved": attention["invariants"]["output_support_preserved"],
            "selected_bound": attention["selected_count"] <= max(attention["limits"]["max_selected"], attention["hard_count"]),
            "expected_hard_type": all(_selected_type(attention, edge_type) for edge_type in case.get("required_selected_types", [])),
            "deterministic": result == repeat,
        }
        rows.append({"case_id": case["case_id"], "phenomenon_tags": case.get("phenomenon_tags", []), "checks": checks, "case_ok": all(checks.values()), "result": result})
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "determinism_accuracy": _ratio(row["checks"]["deterministic"] for row in rows),
        "hard_preservation_accuracy": _ratio(row["checks"]["hard_preserved"] for row in rows),
        "support_preservation_accuracy": _ratio(row["checks"]["support_preserved"] for row in rows),
        "by_tag": _by_tag(rows),
        "claim": "deterministic_bounded_sparse_edge_selector_only",
        "blocked_claims": ["learned_attention", "transformer_attention_equivalence", "llm_quality_parity"],
    }
    _write_jsonl(out / "sparse_attention_rows.jsonl", rows)
    (out / "sparse_attention_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _score_edge(edge: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = nodes[edge["from_node"]]
    target = nodes[edge["to_node"]]
    semantic = _jaccard(source.get("signature_features", []), target.get("signature_features", []))
    lexical = _jaccard(normalize_tokens(source.get("text", "")), normalize_tokens(target.get("text", "")))
    distance = abs(int(source.get("turn_index", 0)) - int(target.get("turn_index", 0)))
    recency = 1.0 / (1.0 + distance)
    role = ROLE_PRIOR.get((source.get("role", ""), target.get("role", "")), 0.35)
    hard = edge["edge_type"] in HARD_EDGE_TYPES
    risk = 1.0 if hard else 0.0
    base = float(edge.get("score", 0.0))
    total = 1.0 if hard else min(0.999999, 0.30 * semantic + 0.25 * lexical + 0.15 * recency + 0.15 * role + 0.15 * base)
    return {
        "candidate_id": f"attn:{edge['edge_id']}",
        "edge_id": edge["edge_id"], "edge_type": edge["edge_type"],
        "from_node": edge["from_node"], "to_node": edge["to_node"],
        "hard": hard, "score": round(total, 6),
        "components": {"semantic": round(semantic, 6), "lexical": round(lexical, 6), "recency": round(recency, 6), "role": role, "risk": risk, "base": base},
        "selected": False, "selection_reason": "unselected",
    }


def _rank_key(row: dict[str, Any]) -> tuple[float, str]:
    return (-float(row["score"]), row["candidate_id"])


def _jaccard(left: Any, right: Any) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _hard_preserved(candidates: list[dict[str, Any]]) -> bool:
    return all(row["selected"] for row in candidates if row["hard"])


def _output_support_preserved(candidates: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> bool:
    outputs = {node["node_id"] for node in nodes if node["node_type"] == "output_chunk"}
    supported = {row["to_node"] for row in candidates if row["selected"] and row["edge_type"] in {"supports_output", "repairs", "requires_evidence"}}
    return outputs <= supported


def _selected_type(attention: dict[str, Any], edge_type: str) -> bool:
    return any(row["selected"] and row["edge_type"] == edge_type for row in attention["candidates"])


def _ratio(values: Any) -> float:
    rows = list(values)
    return round(sum(1 for value in rows if value) / len(rows), 6) if rows else 0.0


def _by_tag(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        for tag in row["phenomenon_tags"]:
            item = result.setdefault(tag, {"case_count": 0, "case_ok": 0})
            item["case_count"] += 1
            item["case_ok"] += int(row["case_ok"])
    for item in result.values():
        item["accuracy"] = round(item["case_ok"] / item["case_count"], 6)
    return result


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
