from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .nl_normalization import normalize_tokens
from .seeded_dialogue import stable_seed
from .semantic_chunk import parse_semantic_chunks
from .sparse_attention import select_sparse_attention
from .topic_continuity_dialogue import detect_contradiction
from lce_validation.runtime.utterance_frame import frame_utterance


GRAPH_SCHEMA_VERSION = "seed_graph_v1_phase1"
CUBE_SCHEMA_VERSION = "cube_view_v1"

NODE_TYPES = [
    "history_chunk",
    "input_chunk",
    "policy_chunk",
    "task_chunk",
    "candidate_chunk",
    "verification_chunk",
    "teacher_chunk",
    "output_chunk",
]

EDGE_TYPES = [
    "overlap",
    "continuation",
    "topic_shift",
    "conflict",
    "requires_evidence",
    "policy_blocks",
    "supports_output",
    "repairs",
    "tests",
]

REQUIRED_CUBE_FACES = [
    "conversation",
    "policy",
    "repair",
    "coding",
    "language",
    "evidence",
]


@dataclass(frozen=True)
class SeedGraphNode:
    node_id: str
    node_type: str
    text: str
    seed: int
    role: str
    source: str
    turn_index: int
    status: str
    language: str = "en"
    task_type: str = "dialogue"
    policy_decision: str = ""
    verification_status: str = ""
    artifact_ref: str = ""
    intent: str = ""
    predicate: str = ""
    semantic_signature: str = ""
    ambiguity_flags: list[str] = field(default_factory=list)
    semantic_ids: list[str] = field(default_factory=list)
    semantic_cube_points: list[dict[str, Any]] = field(default_factory=list)
    parent_ids: list[str] = field(default_factory=list)
    cube_coords: dict[str, str] = field(default_factory=dict)
    view_tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SeedGraphEdge:
    edge_id: str
    edge_type: str
    from_node: str
    to_node: str
    score: float
    reason: str
    selected: bool = True
    cube_coords: dict[str, str] = field(default_factory=dict)
    view_tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CubeFace:
    face_id: str
    axes: list[str]
    include_node_types: list[str]
    include_edge_types: list[str]
    required_visible_edge_types: list[str] = field(default_factory=list)


def build_seed_graph(
    current_input: str,
    history: list[dict[str, str]] | None = None,
    *,
    task_hint: str = "dialogue",
    enable_cube: bool = False,
    attention_limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    history = history or []
    task_type = _infer_task_type(current_input, task_hint)
    policy = _policy_decision(current_input)
    topic = _topic_status(history, current_input)
    route = _route(policy, topic, task_type)
    semantic = parse_semantic_chunks(current_input)
    semantic_frame = frame_utterance(current_input)

    nodes = _build_nodes(current_input, history, task_type, policy, topic, route, enable_cube, semantic, semantic_frame)
    edges = _build_edges(nodes, current_input, history, task_type, policy, topic, route, enable_cube)
    node_rows = [_node_dict(node, enable_cube) for node in nodes]
    edge_rows = [_edge_dict(edge, enable_cube) for edge in edges]
    limits = attention_limits or {}
    attention = select_sparse_attention(
        node_rows, edge_rows,
        max_candidates=int(limits.get("max_candidates", 128)),
        max_selected=int(limits.get("max_selected", 32)),
        top_k_per_target=int(limits.get("top_k_per_target", 4)),
    )
    selected_edges = attention["selected_edge_ids"]
    for edge in edge_rows:
        edge["selected"] = edge["edge_id"] in selected_edges
    output_support = _validate_output_support(nodes, edges, set(selected_edges))
    trace = {
        "ok": output_support["ok"],
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "cube_schema_version": CUBE_SCHEMA_VERSION if enable_cube else "",
        "current_input": current_input,
        "route": route,
        "task_type": task_type,
        "topic_status": topic["status"],
        "policy_decision": policy["decision"],
        "semantic_chunks": semantic["chunks"],
        "semantic_frame": semantic_frame,
        "nodes": node_rows,
        "edges": edge_rows,
        "selected_edge_ids": selected_edges,
        "sparse_attention": attention,
        "output_support": output_support,
        "claim": "seed_graph_v1_phase1_schema_builder_only",
        "blocked_claims": [
            "open_domain_reasoning",
            "llm_quality_parity",
            "transformer_replacement",
            "learned_attention",
            "general_programming_agent",
        ],
    }
    if enable_cube:
        trace["cube"] = build_cube_index(nodes, edges)
    return trace


def build_cube_index(nodes: list[SeedGraphNode], edges: list[SeedGraphEdge]) -> dict[str, Any]:
    faces = _cube_faces()
    cells: list[dict[str, Any]] = []
    for face in faces:
        face_nodes = [node for node in nodes if node.node_type in face.include_node_types]
        face_node_ids = {node.node_id for node in face_nodes}
        face_edges = [
            edge for edge in edges
            if edge.edge_type in face.include_edge_types
            and (edge.from_node in face_node_ids or edge.to_node in face_node_ids)
        ]
        cells.append({
            "face_id": face.face_id,
            "coord": {"face": face.face_id},
            "node_ids": sorted(face_node_ids),
            "edge_ids": sorted(edge.edge_id for edge in face_edges),
            "blocked_count": sum(1 for edge in face_edges if edge.edge_type == "policy_blocks"),
            "unsupported_output_count": 0,
        })
    return {
        "axes": ["turn", "role", "task", "abstraction", "status", "language", "semantic_domain", "semantic_speech_act"],
        "faces": [asdict(face) for face in faces],
        "cells": cells,
    }


def run_seed_graph_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case in load_jsonl(cases_path):
        result = build_seed_graph(
            case["current_input"],
            case.get("history", []),
            task_hint=case.get("task_hint", "dialogue"),
            enable_cube=case.get("enable_cube", False),
        )
        repeat = build_seed_graph(
            case["current_input"],
            case.get("history", []),
            task_hint=case.get("task_hint", "dialogue"),
            enable_cube=case.get("enable_cube", False),
        )
        rows.append({
            "case_id": case["case_id"],
            "route_ok": result["route"] == case["expected_route"],
            "policy_ok": result["policy_decision"] == case["expected_policy_decision"],
            "topic_ok": result["topic_status"] == case["expected_topic_status"],
            "support_ok": result["output_support"]["ok"],
            "deterministic": result == repeat,
            "cube_ok": ("cube" in result) == case.get("enable_cube", False),
            "result": result,
        })
    for row in rows:
        row["case_ok"] = all(row[key] for key in ["route_ok", "policy_ok", "topic_ok", "support_ok", "deterministic", "cube_ok"])
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "determinism_accuracy": _ratio(row["deterministic"] for row in rows),
        "support_accuracy": _ratio(row["support_ok"] for row in rows),
        "claim": "seed_graph_v1_phase1_schema_builder_only",
        "blocked_claims": ["llm_quality_parity", "transformer_replacement"],
    }
    _write_jsonl(out / "seed_graph_rows.jsonl", rows)
    (out / "seed_graph_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _build_nodes(
    current_input: str,
    history: list[dict[str, str]],
    task_type: str,
    policy: dict[str, str],
    topic: dict[str, str],
    route: str,
    enable_cube: bool,
    semantic: dict[str, Any],
    semantic_frame: dict[str, Any],
) -> list[SeedGraphNode]:
    nodes: list[SeedGraphNode] = []
    for index, item in enumerate(history, start=1):
        nodes.append(_node(f"hist-{index:02d}", "history_chunk", item.get("text", ""), item.get("speaker", "user"), "history", index - 1, "accepted", task_type, enable_cube))
    turn = len(history)
    primary_semantic = semantic["chunks"][0] if semantic["chunks"] else {}
    nodes.extend([
        _node(
            "input-01", "input_chunk", current_input, "user", "current_input", turn,
            "active", task_type, enable_cube,
            intent=primary_semantic.get("intent", ""),
            predicate=primary_semantic.get("predicate", ""),
            semantic_signature=primary_semantic.get("semantic_signature", ""),
            ambiguity_flags=primary_semantic.get("ambiguity_flags", []),
            semantic_ids=semantic_frame.get("semantic_ids", []),
            semantic_cube_points=semantic_frame.get("semantic_units", []),
        ),
        _node("policy-01", "policy_chunk", "Do not delete files, send external messages, or bypass evidence gates without approval.", "policy", "default_policy", turn, policy["decision"].lower(), task_type, enable_cube, policy_decision=policy["decision"]),
        _node("task-01", "task_chunk", f"Task type: {task_type}.", "task", "task_classifier", turn, "active", task_type, enable_cube),
        _node("cand-01", "candidate_chunk", _candidate_text(route, task_type), "assistant", "candidate_builder", turn, "candidate", task_type, enable_cube, parent_ids=["input-01"]),
        _node("verif-01", "verification_chunk", f"Route {route}; topic {topic['status']}; policy {policy['decision']}.", "verifier", "seed_graph_verifier", turn, "passed", task_type, enable_cube, verification_status="passed", parent_ids=["cand-01"]),
        _node("teacher-01", "teacher_chunk", "No teacher feedback in this pass.", "teacher", "teacher_feedback", turn, "inactive", task_type, enable_cube),
        _node("out-01", "output_chunk", _output_text(route), "assistant", "output_composer", turn, "emitted", task_type, enable_cube, parent_ids=["cand-01", "verif-01"]),
    ])
    return nodes


def _build_edges(
    nodes: list[SeedGraphNode],
    current_input: str,
    history: list[dict[str, str]],
    task_type: str,
    policy: dict[str, str],
    topic: dict[str, str],
    route: str,
    enable_cube: bool,
) -> list[SeedGraphEdge]:
    edges: list[SeedGraphEdge] = []
    input_tokens = set(normalize_tokens(current_input))
    for node in nodes:
        if node.node_type == "history_chunk":
            overlap = sorted(input_tokens & set(normalize_tokens(node.text)))
            if overlap:
                edges.append(_edge(f"edge-overlap-{node.node_id}", "overlap", node.node_id, "input-01", min(1.0, 0.2 + len(overlap) * 0.1), f"token_overlap:{','.join(overlap[:4])}", enable_cube))
    if history:
        if topic["status"] == "topic_continue":
            edges.append(_edge("edge-continuation-01", "continuation", "hist-01", "input-01", 0.8, topic["reason"], enable_cube))
        elif topic["status"] == "topic_shift":
            edges.append(_edge("edge-topic-shift-01", "topic_shift", "hist-01", "input-01", 0.7, topic["reason"], enable_cube))
    if topic["status"] == "contradiction_repair":
        edges.append(_edge("edge-conflict-01", "conflict", "hist-01", "input-01", 1.0, topic["reason"], enable_cube))
        edges.append(_edge("edge-repairs-01", "repairs", "verif-01", "out-01", 1.0, "repair output required by conflict", enable_cube))
    if policy["decision"] == "DENY":
        edges.append(_edge("edge-policy-blocks-01", "policy_blocks", "policy-01", "cand-01", 1.0, policy["reason"], enable_cube))
    if task_type == "coding":
        edges.append(_edge("edge-tests-01", "tests", "verif-01", "cand-01", 0.9, "bounded coding candidate must be verified", enable_cube))
    if route == "require_evidence":
        edges.append(_edge("edge-requires-evidence-01", "requires_evidence", "policy-01", "out-01", 1.0, policy["reason"], enable_cube))
    edges.append(_edge("edge-supports-output-01", "supports_output", "input-01", "out-01", 0.9, "current input supports emitted output", enable_cube))
    edges.append(_edge("edge-supports-output-02", "supports_output", "verif-01", "out-01", 1.0, "verification supports emitted output", enable_cube))
    return sorted(edges, key=lambda edge: edge.edge_id)


def _node(
    node_id: str,
    node_type: str,
    text: str,
    role: str,
    source: str,
    turn_index: int,
    status: str,
    task_type: str,
    enable_cube: bool,
    *,
    policy_decision: str = "",
    verification_status: str = "",
    parent_ids: list[str] | None = None,
    intent: str = "",
    predicate: str = "",
    semantic_signature: str = "",
    ambiguity_flags: list[str] | None = None,
    semantic_ids: list[str] | None = None,
    semantic_cube_points: list[dict[str, Any]] | None = None,
) -> SeedGraphNode:
    language = _language(text)
    coords = _cube_coords(role, task_type, node_type, status, language, turn_index) if enable_cube else {}
    if enable_cube and semantic_cube_points:
        primary_coordinates = semantic_cube_points[0].get("coordinates", {})
        coords["semantic_domain"] = str(primary_coordinates.get("domain", "unknown"))
        coords["semantic_speech_act"] = str(primary_coordinates.get("speech_act", "unknown"))
    tags = _view_tags(node_type, role, task_type, status, language) if enable_cube else []
    return SeedGraphNode(
        node_id=node_id,
        node_type=node_type,
        text=text,
        seed=stable_seed(f"{node_id}:{node_type}:{text}", salt="lce-seed-graph-node-v1"),
        role=role,
        source=source,
        turn_index=turn_index,
        status=status,
        language=language,
        task_type=task_type,
        policy_decision=policy_decision,
        verification_status=verification_status,
        intent=intent,
        predicate=predicate,
        semantic_signature=semantic_signature,
        ambiguity_flags=ambiguity_flags or [],
        semantic_ids=list(semantic_ids or []),
        semantic_cube_points=[dict(point) for point in semantic_cube_points or []],
        parent_ids=parent_ids or [],
        cube_coords=coords,
        view_tags=tags,
    )


def _edge(edge_id: str, edge_type: str, from_node: str, to_node: str, score: float, reason: str, enable_cube: bool) -> SeedGraphEdge:
    tags = _edge_view_tags(edge_type) if enable_cube else []
    coords = {"status": "active", "abstraction": "relation"} if enable_cube else {}
    return SeedGraphEdge(edge_id, edge_type, from_node, to_node, score, reason, True, coords, tags)


def _node_dict(node: SeedGraphNode, include_cube: bool) -> dict[str, Any]:
    data = asdict(node)
    if not include_cube:
        data.pop("cube_coords", None)
        data.pop("view_tags", None)
    return data


def _edge_dict(edge: SeedGraphEdge, include_cube: bool) -> dict[str, Any]:
    data = asdict(edge)
    if not include_cube:
        data.pop("cube_coords", None)
        data.pop("view_tags", None)
    return data


def _validate_output_support(nodes: list[SeedGraphNode], edges: list[SeedGraphEdge], selected_ids: set[str] | None = None) -> dict[str, Any]:
    output_ids = [node.node_id for node in nodes if node.node_type == "output_chunk"]
    supported = {
        edge.to_node for edge in edges
        if edge.edge_type in {"supports_output", "repairs", "requires_evidence"}
        and (selected_ids is None or edge.edge_id in selected_ids)
    }
    unsupported = sorted(node_id for node_id in output_ids if node_id not in supported)
    return {"ok": not unsupported, "unsupported_output_ids": unsupported, "output_count": len(output_ids)}


def _policy_decision(text: str) -> dict[str, str]:
    lowered = text.lower()
    approval_present = "approval" in lowered and not any(
        phrase in lowered for phrase in ("without approval", "no approval", "approval absent")
    )
    confirmation_present = "confirm" in lowered and not any(
        phrase in lowered for phrase in ("without confirmation", "no confirmation")
    )
    if "delete" in lowered and not approval_present:
        return {"decision": "DENY", "reason": "delete action requested without approval"}
    if ("external" in lowered or "send" in lowered) and not approval_present and not confirmation_present:
        return {"decision": "DENY", "reason": "external action requested without confirmation"}
    evidence_terms = ("evidence", "source", "provenance", "citation")
    request_terms = ("show", "provide", "give", "attach", "identify", "request")
    if any(term in lowered for term in evidence_terms) and any(term in lowered for term in request_terms):
        return {"decision": "REQUIRE_EVIDENCE", "reason": "evidence request requires a registered source node"}
    return {"decision": "ALLOW", "reason": "no blocking policy pattern detected"}


def _topic_status(history: list[dict[str, str]], current_input: str) -> dict[str, str]:
    if not history:
        return {"status": "no_history", "reason": "no history chunks are available"}
    history_text = " ".join(item.get("text", "") for item in history).lower()
    contradiction = detect_contradiction(history_text, current_input.lower())
    if contradiction:
        return {"status": "contradiction_repair", "reason": contradiction}
    current_tokens = set(normalize_tokens(current_input))
    history_tokens = set(normalize_tokens(history_text))
    if current_tokens & history_tokens or "continue" in current_input.lower():
        return {"status": "topic_continue", "reason": "input overlaps with carried history"}
    return {"status": "topic_shift", "reason": "input starts a new branch"}


def _route(policy: dict[str, str], topic: dict[str, str], task_type: str) -> str:
    if policy["decision"] == "DENY":
        return "deny"
    if policy["decision"] == "REQUIRE_EVIDENCE":
        return "require_evidence"
    if topic["status"] == "contradiction_repair":
        return "contradiction_repair"
    if task_type == "coding":
        return "coding_graph"
    if topic["status"] == "topic_shift":
        return "topic_shift"
    return "topic_continue" if topic["status"] == "topic_continue" else "continue"


def _infer_task_type(text: str, task_hint: str) -> str:
    lowered = text.lower()
    if task_hint == "coding" or "function" in lowered or "python" in lowered or "solve(" in lowered:
        return "coding"
    if "policy" in lowered or "rule" in lowered:
        return "policy"
    return "dialogue"


def _candidate_text(route: str, task_type: str) -> str:
    if route == "deny":
        return "Candidate blocked by policy."
    if route == "contradiction_repair":
        return "Candidate asks for contradiction repair."
    if task_type == "coding":
        return "Candidate bounded coding plan with verification node."
    return "Candidate dialogue response from selected graph."


def _output_text(route: str) -> str:
    outputs = {
        "deny": "Policy blocks this action.",
        "require_evidence": "Evidence is required before answering.",
        "contradiction_repair": "Contradiction repair is required before normal composition.",
        "coding_graph": "Coding task graph created with verification support.",
        "topic_shift": "New topic branch created.",
        "topic_continue": "Continue from supported history and input chunks.",
        "continue": "Compose from current input chunks.",
    }
    return outputs[route]


def _language(text: str) -> str:
    if any(ord(char) > 127 for char in text):
        return "mixed"
    return "en"


def _cube_coords(role: str, task_type: str, node_type: str, status: str, language: str, turn_index: int) -> dict[str, str]:
    return {
        "turn": str(turn_index),
        "role": role,
        "task": task_type,
        "abstraction": node_type.replace("_chunk", ""),
        "status": status,
        "language": language,
    }


def _view_tags(node_type: str, role: str, task_type: str, status: str, language: str) -> list[str]:
    tags = ["conversation"]
    if role == "policy" or status in {"deny", "require_evidence"}:
        tags.append("policy")
    if status in {"repaired", "failed"} or node_type in {"verification_chunk", "teacher_chunk"}:
        tags.append("repair")
    if task_type == "coding":
        tags.append("coding")
    if language != "en":
        tags.append("language")
    if node_type in {"verification_chunk", "output_chunk"}:
        tags.append("evidence")
    return sorted(set(tags))


def _edge_view_tags(edge_type: str) -> list[str]:
    tags = ["conversation"]
    if edge_type in {"policy_blocks", "requires_evidence"}:
        tags.append("policy")
    if edge_type in {"conflict", "repairs"}:
        tags.append("repair")
    if edge_type == "tests":
        tags.append("coding")
    if edge_type in {"supports_output", "requires_evidence"}:
        tags.append("evidence")
    return sorted(set(tags))


def _cube_faces() -> list[CubeFace]:
    return [
        CubeFace("conversation", ["turn", "role"], ["history_chunk", "input_chunk", "candidate_chunk", "output_chunk"], ["overlap", "continuation", "topic_shift", "supports_output"]),
        CubeFace("policy", ["task", "status"], ["policy_chunk", "candidate_chunk", "output_chunk"], ["policy_blocks", "requires_evidence", "supports_output"], ["policy_blocks"]),
        CubeFace("repair", ["status", "role"], ["history_chunk", "input_chunk", "verification_chunk", "teacher_chunk", "output_chunk"], ["conflict", "repairs", "supports_output"], ["conflict", "repairs"]),
        CubeFace("coding", ["task", "status"], ["task_chunk", "candidate_chunk", "verification_chunk", "teacher_chunk", "output_chunk"], ["tests", "supports_output", "repairs"]),
        CubeFace("language", ["language", "role"], NODE_TYPES, EDGE_TYPES),
        CubeFace("evidence", ["status", "abstraction"], ["input_chunk", "policy_chunk", "verification_chunk", "output_chunk"], ["supports_output", "requires_evidence", "tests"]),
    ]


def _ratio(values: Any) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return round(sum(1 for value in vals if value) / len(vals), 6)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
