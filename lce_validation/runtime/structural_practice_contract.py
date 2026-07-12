"""Component boundary, ownership, dependency, and invariant practice contract."""
from __future__ import annotations

from typing import Any, Mapping


def evaluate_structure_practice(structure: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    components = structure.get("components") if isinstance(structure, Mapping) else None
    edges = structure.get("dependencies") if isinstance(structure, Mapping) else None
    invariants = structure.get("invariants") if isinstance(structure, Mapping) else None
    if not isinstance(components, list) or not components: return _result(["MISSING_COMPONENTS"])
    ids: set[str] = set()
    for component in components:
        if not isinstance(component, Mapping) or {"component_id", "responsibility", "owner", "inputs", "outputs"} - set(component):
            reasons.append("INVALID_COMPONENT")
            continue
        identifier = component["component_id"]
        if not isinstance(identifier, str) or identifier in ids or not component["responsibility"] or not component["owner"]:
            reasons.append("AMBIGUOUS_COMPONENT_OWNERSHIP")
        ids.add(identifier)
    graph: dict[str, set[str]] = {identifier: set() for identifier in ids}
    if not isinstance(edges, list): reasons.append("INVALID_DEPENDENCIES")
    else:
        for edge in edges:
            if not isinstance(edge, Mapping) or {"from", "to", "kind"} - set(edge) or edge["from"] not in ids or edge["to"] not in ids or edge["from"] == edge["to"]:
                reasons.append("INVALID_DEPENDENCY_EDGE")
                continue
            graph[edge["from"]].add(edge["to"])
    if _has_cycle(graph): reasons.append("CYCLIC_DEPENDENCY")
    if not isinstance(invariants, list) or not invariants or any(not isinstance(item, Mapping) or {"invariant_id", "statement", "verification_ref"} - set(item) or not item["verification_ref"] for item in invariants):
        reasons.append("UNVERIFIED_INVARIANTS")
    return _result(reasons)


def _has_cycle(graph: dict[str, set[str]]) -> bool:
    visiting: set[str] = set(); visited: set[str] = set()
    def visit(node: str) -> bool:
        if node in visiting: return True
        if node in visited: return False
        visiting.add(node)
        result = any(visit(child) for child in graph[node])
        visiting.remove(node); visited.add(node)
        return result
    return any(visit(node) for node in graph)


def _result(reasons: list[str]) -> dict[str, Any]:
    reasons = sorted(set(reasons))
    return {"decision": "GO" if not reasons else "NO_GO", "reasons": reasons, "claim_boundary": "Structural-process evaluation only; runtime behavior requires separate integration evidence."}
