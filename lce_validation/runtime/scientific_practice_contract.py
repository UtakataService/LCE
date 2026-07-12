"""Auditable practice contracts for bounded mathematical and scientific work."""
from __future__ import annotations

from typing import Any, Mapping


DOMAINS = {"mathematics", "physics", "science", "chemistry", "biology"}
REQUIRED_INQUIRY = {
    "inquiry_id",
    "question",
    "claims",
    "assumptions",
    "scope",
    "uncertainty",
    "evidence",
}
REQUIRED_EVIDENCE = {"evidence_id", "kind", "summary", "supports"}


def evaluate_scientific_practice(domain: str, inquiry: Mapping[str, Any]) -> dict[str, Any]:
    """Check whether a bounded inquiry supplies the practice evidence its domain needs.

    This validator checks process structure only. It does not establish that a
    proof is sound, a model is accurate, or an experiment is safe to perform.
    """
    reasons: list[str] = []
    if domain not in DOMAINS:
        return _result(domain, ["UNSUPPORTED_DOMAIN"])
    if not isinstance(inquiry, Mapping) or REQUIRED_INQUIRY - set(inquiry):
        return _result(domain, ["INCOMPLETE_INQUIRY"])

    for field in ("claims", "assumptions", "scope", "uncertainty", "evidence"):
        if not isinstance(inquiry[field], list):
            reasons.append(f"INVALID_{field.upper()}")
    if not isinstance(inquiry["question"], str) or not inquiry["question"].strip():
        reasons.append("QUESTION_NOT_EXPLICIT")
    if not inquiry["claims"] or not inquiry["scope"] or not inquiry["uncertainty"]:
        reasons.append("INQUIRY_BOUNDARY_NOT_EXPLICIT")

    evidence = inquiry["evidence"] if isinstance(inquiry["evidence"], list) else []
    evidence_ids: set[str] = set()
    for item in evidence:
        if not isinstance(item, Mapping) or REQUIRED_EVIDENCE - set(item):
            reasons.append("INVALID_EVIDENCE_ITEM")
            continue
        if not isinstance(item["evidence_id"], str) or not item["evidence_id"]:
            reasons.append("INVALID_EVIDENCE_ID")
        else:
            evidence_ids.add(item["evidence_id"])
        if not isinstance(item["supports"], list) or not item["supports"]:
            reasons.append("UNLINKED_EVIDENCE")
    if not evidence:
        reasons.append("MISSING_EVIDENCE")

    claims = inquiry["claims"] if isinstance(inquiry["claims"], list) else []
    for claim in claims:
        if not isinstance(claim, Mapping) or not isinstance(claim.get("claim_id"), str) or not claim["claim_id"]:
            reasons.append("INVALID_CLAIM")
            continue
        refs = claim.get("evidence_refs")
        if not isinstance(refs, list) or not refs or not set(refs).issubset(evidence_ids):
            reasons.append("CLAIM_EVIDENCE_GAP")

    _apply_domain_gates(domain, inquiry, reasons)
    return _result(domain, reasons)


def _apply_domain_gates(domain: str, inquiry: Mapping[str, Any], reasons: list[str]) -> None:
    method = inquiry.get("method")
    if not isinstance(method, Mapping):
        reasons.append("MISSING_METHOD")
        return
    if domain == "mathematics":
        _require(method, {"definitions", "derivation", "proof_obligations", "counterexample_search"}, "MATH", reasons)
        if not isinstance(method.get("proof_obligations"), list) or not method["proof_obligations"]:
            reasons.append("MATH_PROOF_OBLIGATIONS_MISSING")
    elif domain == "physics":
        _require(method, {"variables", "units", "model", "predictions", "test_plan"}, "PHYSICS", reasons)
        if not isinstance(method.get("variables"), list) or not method["variables"]:
            reasons.append("PHYSICS_VARIABLES_MISSING")
        if not isinstance(method.get("units"), Mapping) or not method["units"]:
            reasons.append("PHYSICS_UNITS_MISSING")
    elif domain == "science":
        _require(method, {"hypothesis", "falsifiers", "observations", "controls", "analysis_plan"}, "SCIENCE", reasons)
        if not isinstance(method.get("falsifiers"), list) or not method["falsifiers"]:
            reasons.append("SCIENCE_FALSIFIERS_MISSING")
    elif domain == "chemistry":
        _require(method, {"species", "conditions", "conservation_checks", "measurement_plan", "safety_boundary"}, "CHEMISTRY", reasons)
        if not isinstance(method.get("conservation_checks"), list) or not method["conservation_checks"]:
            reasons.append("CHEMISTRY_CONSERVATION_CHECK_MISSING")
        if not isinstance(method.get("safety_boundary"), str) or not method["safety_boundary"].strip():
            reasons.append("CHEMISTRY_SAFETY_BOUNDARY_MISSING")
    elif domain == "biology":
        _require(method, {"system", "level_of_organization", "variation_plan", "controls", "ethics_boundary"}, "BIOLOGY", reasons)
        if not isinstance(method.get("variation_plan"), list) or not method["variation_plan"]:
            reasons.append("BIOLOGY_VARIATION_PLAN_MISSING")
        if not isinstance(method.get("ethics_boundary"), str) or not method["ethics_boundary"].strip():
            reasons.append("BIOLOGY_ETHICS_BOUNDARY_MISSING")


def _require(method: Mapping[str, Any], fields: set[str], prefix: str, reasons: list[str]) -> None:
    missing = fields - set(method)
    if missing:
        reasons.append(f"{prefix}_METHOD_FIELDS_MISSING")


def _result(domain: str, reasons: list[str]) -> dict[str, Any]:
    normalized = set(reasons)
    return {
        "decision": "GO" if not normalized else "NO_GO",
        "domain": domain,
        "reasons": sorted(normalized),
        "claim_boundary": (
            "Practice-contract decision only; it does not prove mathematical soundness, "
            "scientific truth, model accuracy, experimental safety, or regulatory compliance."
        ),
    }
