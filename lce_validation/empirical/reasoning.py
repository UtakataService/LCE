from __future__ import annotations

from typing import Any

from .entailment import infer_support_states


def structural_decide(
    fixture: dict[str, Any],
    state: dict[str, Any],
    selected_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive a bounded decision from representation/evidence features."""
    referents = fixture.get("referent_candidates", [])
    if len(referents) > 1:
        return _decision(fixture, state, selected_evidence, "REPAIR_CLARIFY", "multiple referent candidates require clarification", "ambiguous_referent")

    if not selected_evidence:
        return _decision(fixture, state, selected_evidence, "UNKNOWN_MODEL_GAP", "no selected registered evidence", "no_selected_evidence")

    stale = [row for row in selected_evidence if row.get("current") is False]
    if stale:
        return _decision(fixture, state, selected_evidence, "REPAIR_RETRIEVE", "selected evidence is stale or not current", "stale_evidence")

    support_rows = infer_support_states(fixture, selected_evidence)
    support_states = {row["support_state"] for row in support_rows}
    if "contradicts" in support_states or ("supports" in support_states and "does_not_support" in support_states):
        return _decision(fixture, state, selected_evidence, "REJECT_UNSUPPORTED", "selected evidence contains support conflict", "support_conflict", support_rows)

    if support_states == {"supports"}:
        return _decision(fixture, state, selected_evidence, "ACCEPT_CAVEATED", "all selected current evidence supports the bounded answer", "direct_support", support_rows)

    if support_states == {"does_not_support"}:
        return _decision(fixture, state, selected_evidence, "REJECT_UNSUPPORTED", "selected evidence does not support the requested claim", "unsupported_by_evidence", support_rows)

    return _decision(fixture, state, selected_evidence, "UNKNOWN_MODEL_GAP", "evidence support state is unknown", "missing_support_metadata", support_rows)


def _decision(
    fixture: dict[str, Any],
    state: dict[str, Any],
    selected_evidence: list[dict[str, Any]],
    outcome: str,
    reason: str,
    rule_id: str,
    support_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    expected = fixture.get("expected_outcome")
    return {
        "row_id": f"decision-{fixture['fixture_id']}",
        "row_type": "decision_row",
        "fixture_id": fixture["fixture_id"],
        "candidate_id": "CAND-C05",
        "outcome": outcome,
        "reason": reason,
        "structural_rule_id": rule_id,
        "answer_text": fixture.get("answer_text") if outcome == "ACCEPT_CAVEATED" else None,
        "evidence_refs": [row["evidence_id"] for row in selected_evidence],
        "state_ref": state["row_id"],
        "status": "pass" if expected is None or outcome == expected else "blocked",
        "known_gaps": [] if expected is None or outcome == expected else [f"expected={expected}; observed={outcome}"],
        "decision_inputs": {
            "selected_evidence_count": len(selected_evidence),
            "current_flags": [row.get("current") for row in selected_evidence],
            "support_flags": [row.get("supports") for row in selected_evidence],
            "inferred_support": support_rows or [],
            "referent_candidate_count": len(fixture.get("referent_candidates", [])),
        },
    }
