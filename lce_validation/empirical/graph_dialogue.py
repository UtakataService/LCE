from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .nl_normalization import normalize_tokens
from .seed_graph import build_seed_graph
from .seeded_dialogue import stable_seed


def respond_with_graph_dialogue(
    current_input: str,
    history: list[dict[str, str]] | None = None,
    *,
    enable_cube: bool = False,
) -> dict[str, Any]:
    graph = build_seed_graph(current_input, history or [], enable_cube=enable_cube)
    support_ids = _support_node_ids(graph)
    act = _dialogue_act(current_input, graph)
    output_chunks = _compose_output_chunks(current_input, graph, act, support_ids)
    coherence = _check_graph_dialogue_coherence(graph, output_chunks)
    return {
        "ok": coherence["ok"] and graph["ok"],
        "current_input": current_input,
        "history_turn_count": len(history or []),
        "route": graph["route"],
        "dialogue_act": act,
        "topic_status": graph["topic_status"],
        "policy_decision": graph["policy_decision"],
        "support_node_ids": support_ids,
        "output_chunks": output_chunks,
        "response": " ".join(chunk["text"] for chunk in output_chunks),
        "coherence": coherence,
        "graph": graph,
        "claim": "bounded_graph_dialogue_composition_only",
        "blocked_claims": [
            "open_domain_conversation",
            "general_language_understanding",
            "emotional_understanding",
            "long_term_memory_learning",
            "llm_quality_parity",
            "transformer_replacement",
        ],
    }


def run_graph_dialogue_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case in load_jsonl(cases_path):
        result = respond_with_graph_dialogue(case["current_input"], case.get("history", []), enable_cube=case.get("enable_cube", False))
        repeat = respond_with_graph_dialogue(case["current_input"], case.get("history", []), enable_cube=case.get("enable_cube", False))
        rows.append({
            "case_id": case["case_id"],
            "route_ok": result["route"] == case["expected_route"],
            "act_ok": result["dialogue_act"] == case["expected_dialogue_act"],
            "coherence_ok": result["coherence"]["ok"],
            "deterministic": result == repeat,
            "contains": {item: item.lower() in result["response"].lower() for item in case.get("must_contain", [])},
            "result": result,
        })
    for row in rows:
        row["contains_ok"] = all(row["contains"].values())
        row["case_ok"] = row["route_ok"] and row["act_ok"] and row["coherence_ok"] and row["deterministic"] and row["contains_ok"]
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "determinism_accuracy": _ratio(row["deterministic"] for row in rows),
        "coherence_accuracy": _ratio(row["coherence_ok"] for row in rows),
        "claim": "bounded_graph_dialogue_composition_only",
        "blocked_claims": ["llm_quality_parity", "transformer_replacement"],
    }
    _write_jsonl(out / "graph_dialogue_rows.jsonl", rows)
    (out / "graph_dialogue_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _dialogue_act(text: str, graph: dict[str, Any]) -> str:
    lowered = text.lower()
    tokens = set(normalize_tokens(text))
    if graph["route"] == "deny":
        return "policy_boundary"
    if graph["route"] == "contradiction_repair":
        return "repair_request"
    if graph["route"] == "require_evidence":
        return "evidence_request"
    if graph["route"] == "coding_graph":
        return "coding_scaffold"
    if any(marker in lowered for marker in ["what", "how", "why", "どう", "なに", "何"]):
        return "explain_state"
    if tokens & {"next", "continue", "proceed", "進める", "次"}:
        return "continue_plan"
    return "stateful_answer"


def _compose_output_chunks(text: str, graph: dict[str, Any], act: str, support_ids: list[str]) -> list[dict[str, Any]]:
    route = graph["route"]
    chunks = [
        _out("out-01", "ack", _ack_text(act, route), text, support_ids),
        _out("out-02", "state", _state_text(graph), text, support_ids),
    ]
    if act == "policy_boundary":
        chunks.append(_out("out-03", "boundary", "I will not execute that action; the policy edge blocks the candidate before output composition.", text, support_ids))
    elif act == "repair_request":
        chunks.append(_out("out-03", "repair", "The carried context and the new input conflict, so the next useful step is to resolve that contradiction explicitly.", text, support_ids))
    elif act == "evidence_request":
        chunks.append(_out("out-03", "evidence", "I need an evidence node or source before turning this into a factual answer.", text, support_ids))
    elif act == "coding_scaffold":
        chunks.append(_out("out-03", "coding", "I can route this into a bounded pure-function coding graph with candidate, verification, and output nodes.", text, support_ids))
    elif act == "explain_state":
        chunks.append(_out("out-03", "explain", "The response is based on explicit graph nodes and selected support edges, not a hidden chat state.", text, support_ids))
    else:
        chunks.append(_out("out-03", "answer", _answer_text(text, graph), text, support_ids))
    chunks.append(_out("out-04", "next_step", _next_step_text(act), text, support_ids))
    return chunks


def _ack_text(act: str, route: str) -> str:
    if act == "policy_boundary":
        return "I found a policy boundary in the graph."
    if act == "repair_request":
        return "I found a contradiction that should be repaired first."
    if act == "coding_scaffold":
        return "I can map this into the coding graph path."
    if act == "explain_state":
        return "Here is the current graph-backed state."
    return "I can continue from the current supported context."


def _state_text(graph: dict[str, Any]) -> str:
    return f"Route={graph['route']}; topic={graph['topic_status']}; policy={graph['policy_decision']}; support={graph['output_support']['output_count']} output chunk."


def _answer_text(text: str, graph: dict[str, Any]) -> str:
    if graph["topic_status"] == "topic_continue":
        return "The safest continuation is to keep the prior topic active and compose from the current input plus carried history."
    if graph["topic_status"] == "topic_shift":
        return "This looks like a new branch, so I will keep older history available but avoid forcing it into the answer."
    return "The answer can be composed from the current input graph, with policy and support checks left visible."


def _next_step_text(act: str) -> str:
    steps = {
        "policy_boundary": "Next: provide approval/evidence or change the requested action.",
        "repair_request": "Next: choose which rule or statement should remain authoritative.",
        "evidence_request": "Next: attach a source or narrow the claim.",
        "coding_scaffold": "Next: generate or test only a small pure function.",
        "explain_state": "Next: inspect the graph trace or switch to Cube view once the UI exposes it.",
        "continue_plan": "Next: continue with the active graph branch.",
        "stateful_answer": "Next: add more specific constraints if you want a narrower response.",
    }
    return steps[act]


def _support_node_ids(graph: dict[str, Any]) -> list[str]:
    ids = {
        edge["from_node"]
        for edge in graph["edges"]
        if edge["edge_type"] in {"supports_output", "repairs", "requires_evidence"} and edge["to_node"].startswith("out-")
    }
    return sorted(ids)


def _check_graph_dialogue_coherence(graph: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    roles = [chunk["role"] for chunk in chunks]
    if roles[:2] != ["ack", "state"]:
        errors.append("missing_ack_state_prefix")
    if graph["route"] == "deny" and "boundary" not in roles:
        errors.append("missing_policy_boundary")
    if graph["route"] == "contradiction_repair" and "repair" not in roles:
        errors.append("missing_repair_chunk")
    if not all(chunk["support_node_ids"] for chunk in chunks):
        errors.append("missing_chunk_support")
    return {"ok": not errors, "errors": errors, "output_chunk_count": len(chunks)}


def _out(chunk_id: str, role: str, text: str, seed_basis: str, support_ids: list[str]) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "role": role,
        "seed": stable_seed(f"{chunk_id}:{role}:{text}:{seed_basis}", salt="lce-graph-dialogue-v1"),
        "support_node_ids": support_ids,
        "text": text,
    }


def _ratio(values: Any) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return round(sum(1 for value in vals if value) / len(vals), 6)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
