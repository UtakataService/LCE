from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .neural_candidate import generate_neural_candidates
from .seed_graph import build_seed_graph
from .seeded_dialogue import stable_seed


REASONING_VERSION = "graph_reasoning_repair_v4"
CUBE_PATH_VERSION = "cube_reasoning_path_v1"
MAX_STEPS = 4
MAX_POINTS = 64
MAX_LINES = 128


def run_graph_reasoning(
    current_input: str,
    history: list[dict[str, str]] | None = None,
    *,
    candidate_backend: str = "heuristic",
    max_steps: int = MAX_STEPS,
) -> dict[str, Any]:
    step_limit = max(1, min(MAX_STEPS, int(max_steps)))
    graph = build_seed_graph(current_input, history or [], enable_cube=True)
    proposals = generate_neural_candidates(current_input, backend=candidate_backend)
    steps = _build_steps(graph, proposals, step_limit)
    points, lines = _build_path(graph, proposals, steps)
    points = points[:MAX_POINTS]
    point_ids = {point["point_id"] for point in points}
    lines = [line for line in lines if line["from_point"] in point_ids and line["to_point"] in point_ids][:MAX_LINES]
    outcome = _outcome(graph, proposals)
    validation = _validate_reasoning(graph, proposals, steps, points, lines, outcome)
    cube_path = project_reasoning_cube(points, lines)
    cube_validation = _validate_cube_projection(points, lines, cube_path, graph)
    response, output_chunks = _compose_response(outcome, graph, proposals, steps)
    return {
        "ok": validation["ok"] and cube_validation["ok"],
        "reasoning_version": REASONING_VERSION,
        "current_input": current_input,
        "route": graph["route"],
        "outcome": outcome,
        "steps": steps,
        "step_count": len(steps),
        "points": points,
        "lines": lines,
        "point_count": len(points),
        "line_count": len(lines),
        "cube_path": cube_path,
        "validation": validation,
        "cube_validation": cube_validation,
        "graph": graph,
        "neural_candidates": proposals,
        "response": response,
        "output_chunks": output_chunks,
        "limits": {"max_steps": MAX_STEPS, "max_points": MAX_POINTS, "max_lines": MAX_LINES},
        "claim": "bounded_explicit_graph_reasoning_and_cube_projection_only",
        "blocked_claims": [
            "hidden_chain_of_thought", "general_reasoning", "autonomous_agent",
            "cube_creates_reasoning", "llm_quality_parity", "transformer_replacement",
        ],
    }


def project_reasoning_cube(points: list[dict[str, Any]], lines: list[dict[str, Any]]) -> dict[str, Any]:
    faces = {name: {"point_ids": [], "line_ids": []} for name in ("conversation", "policy", "repair", "coding", "language", "evidence")}
    for point in points:
        for face in _point_faces(point):
            faces[face]["point_ids"].append(point["point_id"])
    point_faces = {point_id: face for face, cell in faces.items() for point_id in cell["point_ids"]}
    for line in lines:
        targets = {_line_face(line), point_faces.get(line["from_point"]), point_faces.get(line["to_point"])} - {None}
        for face in sorted(targets):
            faces[face]["line_ids"].append(line["line_id"])
    for cell in faces.values():
        cell["point_ids"] = sorted(set(cell["point_ids"]))
        cell["line_ids"] = sorted(set(cell["line_ids"]))
    return {
        "cube_path_version": CUBE_PATH_VERSION,
        "axes": ["step", "role", "task", "abstraction", "status", "language"],
        "faces": faces,
        "source_point_ids": sorted(point["point_id"] for point in points),
        "source_line_ids": sorted(line["line_id"] for line in lines),
        "projection_only": True,
    }


def run_graph_reasoning_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in load_jsonl(cases_path):
        result = run_graph_reasoning(case["current_input"], case.get("history", []), max_steps=case.get("max_steps", MAX_STEPS))
        repeat = run_graph_reasoning(case["current_input"], case.get("history", []), max_steps=case.get("max_steps", MAX_STEPS))
        checks = {
            "route": result["route"] == case["expected_route"],
            "outcome": result["outcome"] == case["expected_outcome"],
            "reasoning": result["validation"]["ok"],
            "cube": result["cube_validation"]["ok"],
            "bounded": result["step_count"] <= MAX_STEPS and result["point_count"] <= MAX_POINTS and result["line_count"] <= MAX_LINES,
            "deterministic": _stable_view(result) == _stable_view(repeat),
        }
        rows.append({"case_id": case["case_id"], "phenomenon_tags": case.get("phenomenon_tags", []), "checks": checks, "case_ok": all(checks.values()), "result": result})
    summary = {
        "ok": all(row["case_ok"] for row in rows), "run_id": out.name,
        "case_count": len(rows), "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "determinism_accuracy": _ratio(row["checks"]["deterministic"] for row in rows),
        "cube_accuracy": _ratio(row["checks"]["cube"] for row in rows),
        "repair_accuracy": _ratio(row["checks"]["outcome"] for row in rows if "repair" in row["phenomenon_tags"]),
        "by_tag": _by_tag(rows),
        "claim": "bounded_explicit_graph_reasoning_and_cube_projection_only",
        "blocked_claims": ["general_reasoning", "autonomous_agent", "cube_creates_reasoning", "llm_quality_parity"],
    }
    _write_jsonl(out / "graph_reasoning_rows.jsonl", rows)
    (out / "graph_reasoning_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _build_steps(graph: dict[str, Any], proposals: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    plan = [
        ("observe", "parsed semantic chunks and policy state"),
        ("attend", f"selected {len(graph['selected_edge_ids'])} Seed Graph edges"),
        ("propose", f"considered {len(proposals['candidates'])} bounded candidates"),
        ("verify_or_repair", _step_decision_text(graph, proposals)),
    ]
    return [
        {"step_id": f"step-{index:02d}", "index": index, "phase": phase, "status": "completed", "summary": summary,
         "seed": stable_seed(f"{graph['current_input']}:{phase}:{summary}", salt="lce-reasoning-step-v4")}
        for index, (phase, summary) in enumerate(plan[:limit], start=1)
    ]


def _build_path(graph: dict[str, Any], proposals: dict[str, Any], steps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    points = []
    for node in graph["nodes"]:
        if node["node_id"] in graph["sparse_attention"]["active_node_ids"]:
            points.append(_point(f"graph:{node['node_id']}", "graph_node", node["node_type"], node.get("role", "system"), node.get("status", "active"), node.get("language", "en"), 0, node.get("cube_coords", {})))
    for step in steps:
        points.append(_point(f"reason:{step['step_id']}", "reasoning_step", step["phase"], "reasoner", step["status"], "en", step["index"], {"task": graph["task_type"], "abstraction": "reasoning"}))
    for candidate in proposals["candidates"]:
        points.append(_point(f"candidate:{candidate['candidate_id']}", "candidate", candidate["label"], "model" if candidate["backend"] == "ollama_embedding" else "candidate_builder", "proposed", "en", 3, {"task": graph["task_type"], "abstraction": "candidate"}))

    lines = []
    for edge in graph["edges"]:
        if edge["selected"]:
            lines.append(_line(f"graph:{edge['edge_id']}", edge["edge_type"], f"graph:{edge['from_node']}", f"graph:{edge['to_node']}", "seed_graph_selected_edge", edge.get("score", 0.0)))
    step_ids = [f"reason:{step['step_id']}" for step in steps]
    if step_ids and any(point["point_id"] == "graph:input-01" for point in points):
        lines.append(_line("reason:input-observe", "observes", "graph:input-01", step_ids[0], "input starts reasoning path", 1.0))
    for left, right in zip(step_ids, step_ids[1:]):
        lines.append(_line(f"reason:{left}->{right}", "next_step", left, right, "bounded state transition", 1.0))
    propose_point = next((point for point in step_ids if point.endswith("step-03")), None)
    if propose_point:
        for candidate in proposals["candidates"]:
            lines.append(_line(f"reason:proposes:{candidate['candidate_id']}", "proposes", propose_point, f"candidate:{candidate['candidate_id']}", candidate["provenance"], candidate["score"]))
    final_step = step_ids[-1] if step_ids else ""
    if final_step and any(point["point_id"] == "graph:out-01" for point in points):
        lines.append(_line("reason:final-output", "supports_output", final_step, "graph:out-01", "verified or repair outcome supports bounded response", 1.0))
    return points, lines


def _outcome(graph: dict[str, Any], proposals: dict[str, Any]) -> str:
    if graph["policy_decision"] == "DENY":
        return "blocked_policy"
    if graph["route"] == "require_evidence":
        return "repair_evidence"
    if graph["route"] == "contradiction_repair":
        return "repair_conflict"
    if proposals["authority_decision"] == "ABSTAIN":
        return "repair_clarify"
    return "accepted_candidate"


def _validate_reasoning(graph: dict[str, Any], proposals: dict[str, Any], steps: list[dict[str, Any]], points: list[dict[str, Any]], lines: list[dict[str, Any]], outcome: str) -> dict[str, Any]:
    errors = []
    if len(steps) > MAX_STEPS:
        errors.append("step_limit_exceeded")
    if len({step["step_id"] for step in steps}) != len(steps):
        errors.append("duplicate_step")
    if graph["policy_decision"] == "DENY" and outcome != "blocked_policy":
        errors.append("policy_bypass")
    if not graph["output_support"]["ok"]:
        errors.append("graph_output_unsupported")
    if not any(line["line_type"] == "supports_output" and line["to_point"] == "graph:out-01" for line in lines):
        errors.append("reasoning_output_support_missing")
    return {"ok": not errors, "errors": errors, "termination": "bounded_step_limit", "outcome": outcome}


def _validate_cube_projection(points: list[dict[str, Any]], lines: list[dict[str, Any]], cube: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    source_points = {point["point_id"] for point in points}
    source_lines = {line["line_id"] for line in lines}
    projected_points = {item for cell in cube["faces"].values() for item in cell["point_ids"]}
    projected_lines = {item for cell in cube["faces"].values() for item in cell["line_ids"]}
    errors = []
    if not projected_points <= source_points:
        errors.append("cube_created_point")
    if not projected_lines <= source_lines:
        errors.append("cube_created_line")
    if graph["policy_decision"] == "DENY":
        policy_lines = cube["faces"]["policy"]["line_ids"]
        if not any("policy" in line_id for line_id in policy_lines):
            errors.append("policy_line_hidden")
    return {"ok": not errors, "errors": errors, "projection_only": cube["projection_only"], "visible_point_count": len(projected_points), "visible_line_count": len(projected_lines)}


def _compose_response(outcome: str, graph: dict[str, Any], proposals: dict[str, Any], steps: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    text = {
        "blocked_policy": "The reasoning path is blocked by policy; no candidate may bypass the policy point and line.",
        "repair_evidence": "The path requires an evidence repair before a normal answer can be accepted.",
        "repair_conflict": "The path detected a conflict with accepted history and requires explicit repair.",
        "repair_clarify": "The candidate path is ambiguous and requires clarification before selection.",
        "accepted_candidate": f"The bounded path accepted {proposals['candidates'][0]['label']} for further verified composition.",
    }[outcome]
    chunks = [
        {"chunk_id": "out-01", "role": outcome, "seed": stable_seed(text, salt="lce-reasoning-output-v4"), "text": text},
        {"chunk_id": "out-02", "role": "trace", "seed": stable_seed(outcome, salt="lce-reasoning-trace-v4"), "text": f"route={graph['route']}; steps={len(steps)}; cube=projection-only"},
    ]
    return " ".join(chunk["text"] for chunk in chunks), chunks


def _step_decision_text(graph: dict[str, Any], proposals: dict[str, Any]) -> str:
    return f"route={graph['route']}; policy={graph['policy_decision']}; candidate_authority={proposals['authority_decision']}"


def _point(point_id: str, point_type: str, label: str, role: str, status: str, language: str, step: int, coords: dict[str, str]) -> dict[str, Any]:
    merged = {"step": str(step), "role": role, "task": coords.get("task", "dialogue"), "abstraction": coords.get("abstraction", point_type), "status": status, "language": language}
    return {"point_id": point_id, "point_type": point_type, "label": label, "role": role, "status": status, "cube_coords": merged}


def _line(line_id: str, line_type: str, from_point: str, to_point: str, reason: str, score: float) -> dict[str, Any]:
    return {"line_id": line_id, "line_type": line_type, "from_point": from_point, "to_point": to_point, "reason": reason, "score": round(float(score), 6)}


def _point_faces(point: dict[str, Any]) -> list[str]:
    label = f"{point['point_type']} {point['label']} {point['role']}".lower()
    task = point.get("cube_coords", {}).get("task", "")
    faces = ["conversation"]
    if "policy" in label:
        faces.append("policy")
    if any(word in label for word in ("repair", "verify", "clarify", "conflict")):
        faces.append("repair")
    if "coding" in label or task == "coding":
        faces.append("coding")
    if any(word in label for word in ("language", "semantic", "input")):
        faces.append("language")
    if any(word in label for word in ("evidence", "support", "output")):
        faces.append("evidence")
    return sorted(set(faces))


def _line_face(line: dict[str, Any]) -> str:
    if "policy" in line["line_type"]:
        return "policy"
    if line["line_type"] in {"repairs", "next_step"}:
        return "repair"
    if line["line_type"] in {"requires_evidence", "supports_output", "tests"}:
        return "evidence"
    return "conversation"


def _stable_view(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key not in {"neural_candidates"}} | {
        "neural_candidates": {key: value for key, value in result["neural_candidates"].items() if key != "elapsed_ms"}
    }


def _ratio(values: Any) -> float:
    rows = list(values)
    return round(sum(1 for value in rows if value) / len(rows), 6) if rows else 0.0


def _by_tag(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
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
