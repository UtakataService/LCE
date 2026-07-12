"""Deterministic semantic checks for structured model candidates.

This module deliberately checks only declared policy signals. It does not
claim to infer general intent or prove natural-language entailment.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class StructuredAssuranceError(ValueError):
    pass


_EVIDENCE_DISPOSITIONS = {"supports", "contradicts", "unknown"}


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    claim_id: str
    disposition: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceClaim":
        if not isinstance(value, Mapping):
            raise StructuredAssuranceError("INVALID_EVIDENCE_CLAIM")
        claim = cls(claim_id=value.get("claim_id", ""), disposition=value.get("disposition", ""))
        if not claim.claim_id or claim.disposition not in _EVIDENCE_DISPOSITIONS:
            raise StructuredAssuranceError("INVALID_EVIDENCE_CLAIM")
        return claim


@dataclass(frozen=True, slots=True)
class StructuredAssurancePolicy:
    """Data-backed checks to apply after schema validation.

    Paths address object members with dot notation. Intent terms are lexical
    signals selected by the caller; they are not a general semantic parser.
    """

    policy_id: str
    required_values: dict[str, Any] | None = None
    required_terms: dict[str, tuple[str, ...]] | None = None
    forbidden_terms: tuple[str, ...] = ()
    certainty_path: str | None = None
    known_values: tuple[str, ...] = ("known",)
    evidence_refs_path: str | None = None
    required_evidence_claim_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StructuredAssurancePolicy":
        if not isinstance(value, Mapping):
            raise StructuredAssuranceError("INVALID_ASSURANCE_POLICY")
        required_terms = value.get("required_terms")
        normalized_terms: dict[str, tuple[str, ...]] | None = None
        if required_terms is not None:
            if not isinstance(required_terms, Mapping):
                raise StructuredAssuranceError("INVALID_ASSURANCE_REQUIRED_TERMS")
            normalized_terms = {}
            for path, terms in required_terms.items():
                if not isinstance(path, str) or not isinstance(terms, list) or not all(isinstance(term, str) and term for term in terms):
                    raise StructuredAssuranceError("INVALID_ASSURANCE_REQUIRED_TERMS")
                normalized_terms[path] = tuple(terms)
        policy = cls(
            policy_id=value.get("policy_id", ""),
            required_values=dict(value["required_values"]) if isinstance(value.get("required_values"), Mapping) else value.get("required_values"),
            required_terms=normalized_terms,
            forbidden_terms=tuple(value.get("forbidden_terms", ())),
            certainty_path=value.get("certainty_path"),
            known_values=tuple(value.get("known_values", ("known",))),
            evidence_refs_path=value.get("evidence_refs_path"),
            required_evidence_claim_ids=tuple(value.get("required_evidence_claim_ids", ())),
        )
        _validate_policy(policy)
        return policy


def assess_structured_value(
    value: Mapping[str, Any],
    policy: StructuredAssurancePolicy,
    evidence_claims: Mapping[str, EvidenceClaim | Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a bounded assurance decision for an already schema-valid value."""
    _validate_policy(policy)
    if not isinstance(value, Mapping):
        raise StructuredAssuranceError("INVALID_ASSURANCE_VALUE")
    catalog = _normalize_catalog(evidence_claims or {})
    violations: list[str] = []

    for path, expected in (policy.required_values or {}).items():
        if _read_path(value, path) != expected:
            violations.append(f"INTENT_REQUIRED_VALUE_MISMATCH:{path}")
    for path, terms in (policy.required_terms or {}).items():
        actual = _read_path(value, path)
        if not isinstance(actual, str) or any(term.casefold() not in actual.casefold() for term in terms):
            violations.append(f"INTENT_REQUIRED_TERM_MISSING:{path}")
    flattened = "\n".join(_string_values(value)).casefold()
    for term in policy.forbidden_terms:
        if term.casefold() in flattened:
            violations.append(f"INTENT_FORBIDDEN_TERM_PRESENT:{term}")

    if policy.certainty_path and _read_path(value, policy.certainty_path) in policy.known_values:
        refs = _read_path(value, policy.evidence_refs_path or "")
        if not isinstance(refs, list) or not all(isinstance(ref, str) and ref for ref in refs):
            violations.append("CERTAINTY_EVIDENCE_REFS_MISSING")
        else:
            ref_set = set(refs)
            missing_required = set(policy.required_evidence_claim_ids) - ref_set
            if missing_required:
                violations.append("CERTAINTY_EVIDENCE_REQUIRED_CLAIM_MISSING")
            for ref in sorted(ref_set):
                claim = catalog.get(ref)
                if claim is None:
                    violations.append("CERTAINTY_EVIDENCE_REF_UNKNOWN")
                elif claim.disposition == "contradicts":
                    violations.append("CERTAINTY_EVIDENCE_CONTRADICTED")
                elif claim.disposition != "supports":
                    violations.append("CERTAINTY_EVIDENCE_UNSUPPORTED")

    return {
        "accepted": not violations,
        "policy_id": policy.policy_id,
        "violations": sorted(set(violations)),
        "claim_boundary": "Deterministic declared-signal check only; it does not prove general intent fidelity or natural-language entailment.",
    }


def _validate_policy(policy: StructuredAssurancePolicy) -> None:
    if not isinstance(policy, StructuredAssurancePolicy) or not isinstance(policy.policy_id, str) or not policy.policy_id:
        raise StructuredAssuranceError("INVALID_ASSURANCE_POLICY")
    if not isinstance(policy.required_values, (dict, type(None))) or not isinstance(policy.required_terms, (dict, type(None))):
        raise StructuredAssuranceError("INVALID_ASSURANCE_POLICY")
    if not isinstance(policy.forbidden_terms, tuple) or not all(isinstance(term, str) and term for term in policy.forbidden_terms):
        raise StructuredAssuranceError("INVALID_ASSURANCE_FORBIDDEN_TERMS")
    if not isinstance(policy.known_values, tuple) or not all(isinstance(item, str) and item for item in policy.known_values):
        raise StructuredAssuranceError("INVALID_ASSURANCE_KNOWN_VALUES")
    if not isinstance(policy.required_evidence_claim_ids, tuple) or not all(isinstance(item, str) and item for item in policy.required_evidence_claim_ids):
        raise StructuredAssuranceError("INVALID_ASSURANCE_EVIDENCE_IDS")
    if policy.certainty_path is None:
        if policy.evidence_refs_path or policy.required_evidence_claim_ids:
            raise StructuredAssuranceError("ASSURANCE_EVIDENCE_PATH_REQUIRED")
    elif not isinstance(policy.certainty_path, str) or not isinstance(policy.evidence_refs_path, str) or not policy.evidence_refs_path:
        raise StructuredAssuranceError("ASSURANCE_EVIDENCE_PATH_REQUIRED")
    for path in (policy.required_values or {}):
        if not isinstance(path, str) or not path:
            raise StructuredAssuranceError("INVALID_ASSURANCE_PATH")
    for path, terms in (policy.required_terms or {}).items():
        if not isinstance(path, str) or not path or not isinstance(terms, tuple) or not all(isinstance(term, str) and term for term in terms):
            raise StructuredAssuranceError("INVALID_ASSURANCE_REQUIRED_TERMS")


def _normalize_catalog(source: Mapping[str, EvidenceClaim | Mapping[str, Any]]) -> dict[str, EvidenceClaim]:
    if not isinstance(source, Mapping):
        raise StructuredAssuranceError("INVALID_EVIDENCE_CATALOG")
    catalog: dict[str, EvidenceClaim] = {}
    for claim_id, raw in source.items():
        if not isinstance(claim_id, str) or not claim_id:
            raise StructuredAssuranceError("INVALID_EVIDENCE_CATALOG")
        claim = raw if isinstance(raw, EvidenceClaim) else EvidenceClaim.from_dict(raw)
        if claim.claim_id != claim_id:
            raise StructuredAssuranceError("EVIDENCE_CLAIM_ID_MISMATCH")
        catalog[claim_id] = claim
    return catalog


def _read_path(value: Mapping[str, Any], path: str) -> Any:
    current: Any = value
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return None
        current = current[segment]
    return current


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [item for child in value.values() for item in _string_values(child)]
    if isinstance(value, list):
        return [item for child in value for item in _string_values(child)]
    return []
