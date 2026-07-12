"""Admission control for tentative dialogue hypotheses.

The gate measures decision support, never truth.  A hypothesis can remain in
state for repair while being ineligible as a plan premise.
"""
from __future__ import annotations

from typing import Any, Mapping


DECISION_SUPPORT_THRESHOLD = 0.55
TENTATIVE_RECORD_THRESHOLD = 0.30


def assess_hypothesis(item: Mapping[str, Any]) -> dict[str, Any]:
    """Classify one canonical interpretation without changing it."""
    evidence = item.get("evidence_spans")
    if item.get("status") == "RETRACTED":
        return _assessment(item, "BLOCKED", "RETRACTED")
    if not isinstance(evidence, list) or not evidence:
        return _assessment(item, "UNKNOWN", "NO_EVIDENCE")
    if item.get("kind") == "observed":
        return _assessment(item, "ELIGIBLE", "DIRECT_OBSERVATION")
    confidence = item.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        return _assessment(item, "UNKNOWN", "INVALID_CONFIDENCE")
    if confidence >= DECISION_SUPPORT_THRESHOLD:
        return _assessment(item, "ELIGIBLE", "SUPPORTED_INFERENCE")
    if confidence >= TENTATIVE_RECORD_THRESHOLD:
        return _assessment(item, "TENTATIVE_ONLY", "INSUFFICIENT_DECISION_SUPPORT")
    return _assessment(item, "UNKNOWN", "INSUFFICIENT_SUPPORT")


def assess_hypotheses(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [assess_hypothesis(item) for item in items]


def selected_interpretation_ids(assessments: list[Mapping[str, Any]]) -> list[str]:
    return [str(item["interpretation_id"]) for item in assessments if item["admission"] == "ELIGIBLE"]


def withheld_interpretation_ids(assessments: list[Mapping[str, Any]]) -> list[str]:
    return [str(item["interpretation_id"]) for item in assessments if item["admission"] != "ELIGIBLE"]


def _assessment(item: Mapping[str, Any], admission: str, reason: str) -> dict[str, Any]:
    return {
        "interpretation_id": item.get("id"),
        "admission": admission,
        "reason": reason,
        "confidence": item.get("confidence"),
    }
