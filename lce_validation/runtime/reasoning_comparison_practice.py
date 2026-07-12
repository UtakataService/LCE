"""Reasoning, causal, consistency, comparison, and refutation practice."""
from __future__ import annotations

from typing import Any, Mapping


def evaluate_reasoning_comparison_practice(record: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    premises = record.get("premises") if isinstance(record, Mapping) else None
    conclusion = record.get("conclusion") if isinstance(record, Mapping) else None
    comparison = record.get("comparison") if isinstance(record, Mapping) else None
    refutations = record.get("refutation_checks") if isinstance(record, Mapping) else None
    if not isinstance(premises, list) or not premises or any(not isinstance(item, Mapping) or {"premise_id", "statement", "status"} - set(item) for item in premises):
        reasons.append("INVALID_PREMISES")
        ids: set[str] = set()
    else:
        ids = {str(item["premise_id"]) for item in premises}
        if len(ids) != len(premises): reasons.append("DUPLICATE_PREMISE_ID")
    if not isinstance(conclusion, Mapping) or {"statement", "supporting_premise_ids", "causal_claim"} - set(conclusion):
        reasons.append("INVALID_CONCLUSION")
    else:
        supports = conclusion["supporting_premise_ids"]
        if not isinstance(supports, list) or not supports or not set(supports).issubset(ids): reasons.append("UNSUPPORTED_CONCLUSION")
        if conclusion["causal_claim"]:
            causal = conclusion.get("causal_analysis")
            if not isinstance(causal, Mapping) or {"mechanism", "alternative_causes", "counterfactual"} - set(causal) or not causal["mechanism"] or not causal["alternative_causes"] or not causal["counterfactual"]:
                reasons.append("CAUSAL_CLAIM_NOT_DISCIPLINED")
    if not isinstance(comparison, Mapping) or {"subjects", "axis", "conditions_aligned"} - set(comparison) or not isinstance(comparison.get("subjects"), list) or len(comparison["subjects"]) != 2 or not comparison["axis"] or comparison["conditions_aligned"] is not True:
        reasons.append("INVALID_COMPARISON")
    if not isinstance(refutations, list) or not refutations or any(
        not isinstance(item, Mapping) or not item.get("would_change_conclusion")
        for item in refutations
    ):
        reasons.append("MISSING_REFUTATION_CHECK")
    return _result(reasons)


def _result(reasons: list[str]) -> dict[str, Any]:
    reasons = sorted(set(reasons))
    return {"decision": "GO" if not reasons else "NO_GO", "reasons": reasons, "claim_boundary": "Reasoning-process evaluation only; premises and causal mechanisms still require external validation."}
