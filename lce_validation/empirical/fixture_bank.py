from __future__ import annotations

from typing import Any


def generate_fixture_bank(size_per_family: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(1, size_per_family + 1):
        rows.append(_supported(i))
        rows.append(_overlap_unknown(i))
        rows.append(_unsupported(i))
        rows.append(_stale(i))
        rows.append(_ambiguous(i))
        rows.append(_contradiction(i))
    return rows


def _base(i: int, kind: str, family: str, expected: str, tags: list[str]) -> dict[str, Any]:
    return {
        "fixture_id": f"FX-BANK-{kind.upper()}-{i:03d}",
        "fixture_family": family,
        "candidate_ids": ["CAND-C01", "CAND-C05"],
        "phenomenon_tags": tags,
        "input_payload_ref": f"bank://{kind}-{i:03d}",
        "expected_behavior": f"{kind} fixture generated for deterministic coverage",
        "allowed_outcomes": [expected],
        "disallowed_outcomes": ["ACCEPT_VERIFIED"],
        "gate_assertions": ["V_entailment", "SUFF_DIRECT_SPAN"],
        "baseline_expected_failure_profile": "deterministic fixture-bank coverage case",
        "provenance_ref": "prov-fixture-bank",
        "license_ref": "license_internal_seed",
        "contamination_ref": "contamination_seed_only",
        "label_refs": [f"label-bank-{kind}-{i:03d}"],
        "replay_manifest_ref": "replay-pending",
        "resource_snapshot_ref": "res-pending",
        "status": "gateable",
        "expected_outcome": expected,
    }


def _supported(i: int) -> dict[str, Any]:
    row = _base(i, "supported", "DATA-F-E", "ACCEPT_CAVEATED", ["bank_supported", "inferred_entailment"])
    row.update({
        "question": f"Which port is assigned to service alpha{i}?",
        "answer_text": f"Service alpha{i} uses port {8700 + i}.",
        "required_terms": [f"alpha{i}", str(8700 + i)],
        "evidence_rows": [{
            "evidence_id": f"ev-bank-supported-{i:03d}",
            "text": f"Service registry: alpha{i} is assigned port {8700 + i}; beta{i} is assigned port {8800 + i}.",
            "current": True,
            "selected": True,
            "source_ref": "fixture-bank",
        }],
    })
    return row


def _overlap_unknown(i: int) -> dict[str, Any]:
    row = _base(i, "overlap", "DATA-F-E", "UNKNOWN_MODEL_GAP", ["bank_overlap", "non_entailing_overlap"])
    row.update({
        "question": f"Which port is assigned to service gamma{i}?",
        "required_terms": [f"gamma{i}", str(8900 + i)],
        "evidence_rows": [{
            "evidence_id": f"ev-bank-overlap-{i:03d}",
            "text": f"The service gamma{i} appears in the registry notes, but the assigned port is omitted in this excerpt.",
            "current": True,
            "selected": True,
            "source_ref": "fixture-bank",
        }],
    })
    return row


def _unsupported(i: int) -> dict[str, Any]:
    row = _base(i, "unsupported", "DATA-F-G", "REJECT_UNSUPPORTED", ["bank_unsupported"])
    row.update({
        "question": f"Does fixture bank case {i} prove model replacement?",
        "evidence_rows": [{
            "evidence_id": f"ev-bank-unsupported-{i:03d}",
            "text": "The fixture bank only expands local coverage and does not prove model replacement.",
            "supports": False,
            "current": True,
            "selected": True,
            "source_ref": "fixture-bank",
        }],
    })
    return row


def _stale(i: int) -> dict[str, Any]:
    row = _base(i, "stale", "DATA-F-D", "REPAIR_RETRIEVE", ["bank_stale", "stale_evidence"])
    row.update({
        "question": f"Is service delta{i} currently active?",
        "required_terms": [f"delta{i}", "active"],
        "evidence_rows": [{
            "evidence_id": f"ev-bank-stale-{i:03d}",
            "text": f"A prior snapshot said service delta{i} was active.",
            "current": False,
            "selected": True,
            "source_ref": "fixture-bank-old-snapshot",
        }],
    })
    return row


def _ambiguous(i: int) -> dict[str, Any]:
    row = _base(i, "ambiguous", "DATA-F-B", "REPAIR_CLARIFY", ["bank_ambiguous", "ambiguous_reference"])
    row.update({
        "candidate_ids": ["CAND-C03", "CAND-C10"],
        "question": "Move that to the next step.",
        "referent_candidates": [f"artifact-{i}", f"task-{i}", f"meeting-{i}"],
        "pragmatic_constraints": ["avoid guessing referent"],
        "evidence_rows": [{
            "evidence_id": f"ev-bank-ambiguous-{i:03d}",
            "text": f"artifact-{i}, task-{i}, and meeting-{i} are all active references.",
            "supports": True,
            "current": True,
            "selected": True,
            "source_ref": "fixture-bank",
        }],
    })
    return row


def _contradiction(i: int) -> dict[str, Any]:
    row = _base(i, "contradiction", "DATA-F-C", "REJECT_UNSUPPORTED", ["bank_contradiction", "contradiction"])
    row.update({
        "question": f"Can operation epsilon{i} proceed without approval?",
        "required_terms": [f"epsilon{i}", "approval"],
        "evidence_rows": [{
            "evidence_id": f"ev-bank-contradiction-{i:03d}",
            "text": f"Operation epsilon{i} cannot proceed without approval.",
            "contradicts": True,
            "current": True,
            "selected": True,
            "source_ref": "fixture-bank-policy",
        }],
    })
    return row
