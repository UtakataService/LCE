from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .nl_normalization import normalize_tokens
from .engine import (
    build_state_row,
    build_utterance_row,
    decide,
    fixture_evidence_rows,
    load_jsonl,
    select_evidence,
)


ROUTE_BY_OUTCOME = {
    "ACCEPT_CAVEATED": "answer_with_caveat",
    "REJECT_UNSUPPORTED": "reject_unsupported",
    "REPAIR_RETRIEVE": "retrieve_more_evidence",
    "REPAIR_CLARIFY": "ask_clarifying_question",
    "UNKNOWN_MODEL_GAP": "model_gap",
}


def answer_limited_domain(fixtures_path: str | Path, query: str, out_path: str | Path | None = None) -> dict[str, Any]:
    fixtures = load_jsonl(fixtures_path)
    fixture = _select_fixture(fixtures, query)
    if fixture is None:
        result = {
            "ok": True,
            "query": query,
            "matched_fixture_id": None,
            "route": "out_of_domain",
            "outcome": "UNKNOWN_MODEL_GAP",
            "answer": "The query is outside the loaded limited-domain fixture bank.",
            "evidence_refs": [],
            "claim": "limited_domain_app_only",
            "blocked_claims": ["general_language_understanding", "transformer_replacement", "quality_parity"],
        }
        _write_optional(out_path, result)
        return result

    evidence_rows = fixture_evidence_rows(fixture)
    utterance = build_utterance_row(fixture)
    utterance["raw_text"] = query
    state = build_state_row(fixture, utterance, evidence_rows)
    retrieval, selected = select_evidence(fixture, evidence_rows)
    decision = decide(fixture, state, selected)
    route = ROUTE_BY_OUTCOME.get(decision["outcome"], "model_gap")
    result = {
        "ok": True,
        "query": query,
        "matched_fixture_id": fixture["fixture_id"],
        "match_score": _match_score(query, fixture),
        "route": route,
        "outcome": decision["outcome"],
        "reason": decision["reason"],
        "answer": _answer_text(route, decision, selected),
        "evidence_refs": [row["evidence_id"] for row in selected],
        "decision_inputs": decision.get("decision_inputs", []),
        "claim": "limited_domain_app_only",
        "blocked_claims": ["general_language_understanding", "transformer_replacement", "quality_parity"],
    }
    _write_optional(out_path, result)
    return result


def _select_fixture(fixtures: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    normalized = query.strip().lower()
    for fixture in fixtures:
        if normalized == fixture["fixture_id"].lower():
            return fixture
    scored = sorted(((_match_score(query, fixture), fixture) for fixture in fixtures), key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] <= 0:
        return None
    return scored[0][1]


def _match_score(query: str, fixture: dict[str, Any]) -> int:
    query_tokens = set(_tokens(query))
    fixture_tokens = set(_tokens(fixture.get("question", "")))
    fixture_tokens.update(_tokens(fixture.get("expected_behavior", "")))
    for row in fixture.get("evidence_rows", []):
        fixture_tokens.update(_tokens(row.get("text", "")))
    return len(query_tokens & fixture_tokens)


def _answer_text(route: str, decision: dict[str, Any], selected: list[dict[str, Any]]) -> str:
    if route == "answer_with_caveat":
        text = selected[0].get("text", "") if selected else ""
        return f"Supported within the loaded evidence: {text}"
    if route == "reject_unsupported":
        return f"Rejected because the loaded evidence does not support the claim: {decision['reason']}"
    if route == "retrieve_more_evidence":
        return f"More current or complete evidence is required: {decision['reason']}"
    if route == "ask_clarifying_question":
        return f"Clarification is required before answering: {decision['reason']}"
    return f"The structural kernel cannot decide this case: {decision['reason']}"


def _tokens(text: str) -> list[str]:
    return normalize_tokens(text)


def _write_optional(path: str | Path | None, result: dict[str, Any]) -> None:
    if path is None:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
