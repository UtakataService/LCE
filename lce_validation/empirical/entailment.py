from __future__ import annotations

import re
from typing import Any

STOPWORDS = {
    "a", "an", "and", "are", "as", "be", "does", "for", "is", "it", "of",
    "on", "or", "the", "this", "to", "use", "uses", "what", "which",
}


def infer_support_state(fixture: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Infer bounded support from local lexical/structural features."""
    if evidence.get("contradicts") is True:
        return _state("contradicts", "evidence explicitly marked as contradictory", evidence, 0.0)

    if "supports" in evidence:
        return _state("supports" if evidence.get("supports") is True else "does_not_support", "explicit support metadata", evidence, 1.0)

    text = evidence.get("text", "")
    required_terms = [str(term).lower() for term in fixture.get("required_terms", [])]
    text_tokens = _tokens(text)
    question_tokens = _tokens(fixture.get("question", ""))
    overlap = sorted(question_tokens & text_tokens)
    numeric_question = set(re.findall(r"\d+", fixture.get("question", "")))
    numeric_text = set(re.findall(r"\d+", text))

    if required_terms:
        missing = [term for term in required_terms if term not in text.lower()]
        if not missing:
            return _state("supports", f"required_terms present: {required_terms}", evidence, 0.85, overlap)
        return _state("unknown", f"missing required_terms: {missing}", evidence, 0.25, overlap)

    if numeric_question and not numeric_question <= numeric_text:
        return _state("does_not_support", "question numeric constraints absent from evidence", evidence, 0.55, overlap)

    if len(overlap) >= max(3, min(5, len(question_tokens))):
        return _state("unknown", "lexical overlap without required entailment terms", evidence, 0.35, overlap)

    return _state("unknown", "insufficient lexical evidence for bounded entailment", evidence, 0.1, overlap)


def infer_support_states(fixture: dict[str, Any], evidence_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [infer_support_state(fixture, row) for row in evidence_rows]


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z0-9_]+", text.lower())
        if token and token not in STOPWORDS
    }


def _state(
    support_state: str,
    reason: str,
    evidence: dict[str, Any],
    confidence: float,
    overlap: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence.get("evidence_id"),
        "support_state": support_state,
        "reason": reason,
        "confidence": confidence,
        "lexical_overlap": overlap or [],
    }
