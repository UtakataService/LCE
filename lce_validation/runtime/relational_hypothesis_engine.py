"""Opaque relation frames with bounded hypothesis simulation and verification.

The engine intentionally treats entity and action labels as opaque symbols. It
can reason over declared relations without claiming to know the nouns involved.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


class RelationFrameError(ValueError):
    pass


def run_relational_hypothesis_cycle(frame: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize(frame)
    scenarios = _generate_scenarios(normalized)
    evaluated = [_evaluate_scenario(scenario, normalized) for scenario in scenarios]
    accepted = [item for item in evaluated if item["verdict"] == "ACCEPT"]
    if accepted:
        selected = accepted[0]
        decision = "ACCEPT"
    elif any(item["verdict"] == "REJECT" for item in evaluated):
        selected = next(item for item in evaluated if item["verdict"] == "REJECT")
        decision = "ABSTAIN"
    elif any(item["verdict"] == "CLARIFY" for item in evaluated):
        selected = next(item for item in evaluated if item["verdict"] == "CLARIFY")
        decision = "CLARIFY"
    else:
        selected = evaluated[0]
        decision = "ABSTAIN"
    return {
        "decision": decision,
        "selected_hypothesis_id": selected["hypothesis_id"],
        "selected_outcomes": selected["simulated_outcomes"] if decision == "ACCEPT" else [],
        "public_trace": [{"hypothesis_id": item["hypothesis_id"], "kind": item["kind"], "verdict": item["verdict"], "reason_codes": item["reason_codes"]} for item in evaluated],
        "frame_hash": _hash(normalized),
        "claim_boundary": "Bounded simulation over declared opaque relations only; no real-world causal or lexical understanding claim.",
    }


def _normalize(frame: Mapping[str, Any]) -> dict[str, Any]:
    required = {"actor", "action", "target", "goal", "conditions", "observations", "constraints", "action_catalog"}
    if not isinstance(frame, Mapping) or required - set(frame):
        raise RelationFrameError("INVALID_RELATION_FRAME")
    for field in ("actor", "action", "target", "goal"):
        if not isinstance(frame[field], str) or not frame[field]: raise RelationFrameError("INVALID_RELATION_ROLE")
    for field in ("conditions", "observations", "constraints"):
        if not isinstance(frame[field], list) or not all(isinstance(item, str) and item for item in frame[field]): raise RelationFrameError("INVALID_RELATION_LIST")
    catalog = frame["action_catalog"]
    if not isinstance(catalog, Mapping) or any(not isinstance(key, str) or not isinstance(value, Mapping) for key, value in catalog.items()):
        raise RelationFrameError("INVALID_ACTION_CATALOG")
    return {key: (dict(value) if key == "action_catalog" else list(value) if key in {"conditions", "observations", "constraints"} else value) for key, value in frame.items()}


def _generate_scenarios(frame: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"hypothesis_id": "h-direct", "kind": "direct", "assumed_conditions": list(frame["conditions"])},
        {"hypothesis_id": "h-missing-condition", "kind": "missing_condition", "assumed_conditions": []},
        {"hypothesis_id": "h-constraint-check", "kind": "constraint_check", "assumed_conditions": list(frame["conditions"])},
    ]


def _evaluate_scenario(scenario: Mapping[str, Any], frame: Mapping[str, Any]) -> dict[str, Any]:
    action = frame["action_catalog"].get(frame["action"])
    if not action:
        return _result(scenario, "CLARIFY", ["ACTION_EFFECT_UNKNOWN"], [])
    required = action.get("requires", [])
    effects = action.get("effects", [])
    if not isinstance(required, list) or not isinstance(effects, list):
        return _result(scenario, "CLARIFY", ["ACTION_CATALOG_INVALID"], [])
    assumptions = set(scenario["assumed_conditions"])
    missing = sorted(set(required) - assumptions)
    if missing:
        return _result(scenario, "CLARIFY", ["MISSING_REQUIRED_CONDITION:" + item for item in missing], [])
    conflict = sorted(set(effects) & set(frame["constraints"]))
    if conflict:
        return _result(scenario, "REJECT", ["CONSTRAINT_CONFLICT:" + item for item in conflict], [])
    contradictions = sorted(set(effects) & {"not:" + item for item in frame["observations"]})
    if contradictions:
        return _result(scenario, "REJECT", ["OBSERVATION_CONTRADICTION:" + item for item in contradictions], [])
    return _result(scenario, "ACCEPT", ["SIMULATION_CONDITIONS_MET"], [str(item) for item in effects])


def _result(scenario: Mapping[str, Any], verdict: str, reason_codes: list[str], outcomes: list[str]) -> dict[str, Any]:
    return {"hypothesis_id": scenario["hypothesis_id"], "kind": scenario["kind"], "verdict": verdict, "reason_codes": sorted(reason_codes), "simulated_outcomes": sorted(outcomes)}


def _hash(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
