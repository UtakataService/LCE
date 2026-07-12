"""Model-agnostic assurance gate for typed multimodal candidates.

Adapters convert model, sensor, or rules-engine output into CandidateEnvelope.
This gate verifies declared evidence, hard constraints, and action scope. It
does not perform object recognition, speaker recognition, or game analysis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class CandidateAssuranceError(ValueError):
    pass


_ACTION_SCOPES = ("display", "persist", "state_commit", "external_execution")
_ACTION_SCOPES_REQUIRING_AUTH = {"state_commit", "external_execution"}


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    evidence_id: str
    kind: str
    source_digest: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceArtifact":
        if not isinstance(value, Mapping):
            raise CandidateAssuranceError("INVALID_EVIDENCE_ARTIFACT")
        artifact = cls(value.get("evidence_id", ""), value.get("kind", ""), value.get("source_digest", ""))
        if not all(isinstance(field, str) and field for field in (artifact.evidence_id, artifact.kind, artifact.source_digest)):
            raise CandidateAssuranceError("INVALID_EVIDENCE_ARTIFACT")
        return artifact


@dataclass(frozen=True, slots=True)
class CandidateEnvelope:
    candidate_id: str
    modality: str
    claim_type: str
    value: dict[str, Any]
    confidence: float
    evidence_refs: tuple[str, ...]
    producer_id: str
    input_digest: str
    action_scope: str = "display"
    authorization_ref: str | None = None
    advisory_flags: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CandidateEnvelope":
        if not isinstance(value, Mapping):
            raise CandidateAssuranceError("INVALID_CANDIDATE_ENVELOPE")
        envelope = cls(
            candidate_id=value.get("candidate_id", ""),
            modality=value.get("modality", ""),
            claim_type=value.get("claim_type", ""),
            value=dict(value["value"]) if isinstance(value.get("value"), Mapping) else value.get("value"),
            confidence=value.get("confidence"),
            evidence_refs=tuple(value.get("evidence_refs", ())),
            producer_id=value.get("producer_id", ""),
            input_digest=value.get("input_digest", ""),
            action_scope=value.get("action_scope", "display"),
            authorization_ref=value.get("authorization_ref"),
            advisory_flags=tuple(value.get("advisory_flags", ())),
        )
        _validate_envelope(envelope)
        return envelope


@dataclass(frozen=True, slots=True)
class CandidateAssurancePolicy:
    policy_id: str
    allowed_modalities: tuple[str, ...]
    allowed_claim_types: tuple[str, ...]
    min_confidence: float = 0.0
    required_evidence_kinds: tuple[str, ...] = ()
    required_value_paths: dict[str, Any] | None = None
    allowed_values_by_path: dict[str, tuple[Any, ...]] | None = None
    allowed_action_scopes: tuple[str, ...] = ("display",)
    require_evidence_input_digest_match: bool = False

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CandidateAssurancePolicy":
        if not isinstance(value, Mapping):
            raise CandidateAssuranceError("INVALID_CANDIDATE_ASSURANCE_POLICY")
        allowed_values = value.get("allowed_values_by_path")
        normalized_allowed: dict[str, tuple[Any, ...]] | None = None
        if allowed_values is not None:
            if not isinstance(allowed_values, Mapping):
                raise CandidateAssuranceError("INVALID_ALLOWED_VALUES_POLICY")
            normalized_allowed = {}
            for path, options in allowed_values.items():
                if not isinstance(path, str) or not path or not isinstance(options, list) or not options:
                    raise CandidateAssuranceError("INVALID_ALLOWED_VALUES_POLICY")
                normalized_allowed[path] = tuple(options)
        policy = cls(
            policy_id=value.get("policy_id", ""),
            allowed_modalities=tuple(value.get("allowed_modalities", ())),
            allowed_claim_types=tuple(value.get("allowed_claim_types", ())),
            min_confidence=value.get("min_confidence", 0.0),
            required_evidence_kinds=tuple(value.get("required_evidence_kinds", ())),
            required_value_paths=dict(value["required_value_paths"]) if isinstance(value.get("required_value_paths"), Mapping) else value.get("required_value_paths"),
            allowed_values_by_path=normalized_allowed,
            allowed_action_scopes=tuple(value.get("allowed_action_scopes", ("display",))),
            require_evidence_input_digest_match=value.get("require_evidence_input_digest_match", False),
        )
        _validate_policy(policy)
        return policy


def assess_candidate(
    candidate: CandidateEnvelope | Mapping[str, Any],
    policy: CandidateAssurancePolicy | Mapping[str, Any],
    evidence_catalog: Mapping[str, EvidenceArtifact | Mapping[str, Any]],
) -> dict[str, Any]:
    """Make a bounded ACCEPT/HOLD/REJECT decision for a normalized candidate."""
    envelope = candidate if isinstance(candidate, CandidateEnvelope) else CandidateEnvelope.from_dict(candidate)
    effective_policy = policy if isinstance(policy, CandidateAssurancePolicy) else CandidateAssurancePolicy.from_dict(policy)
    catalog = _normalize_catalog(evidence_catalog)
    reject: list[str] = []
    hold: list[str] = []

    if envelope.modality not in effective_policy.allowed_modalities:
        reject.append("MODALITY_NOT_ALLOWED")
    if envelope.claim_type not in effective_policy.allowed_claim_types:
        reject.append("CLAIM_TYPE_NOT_ALLOWED")
    if envelope.action_scope not in effective_policy.allowed_action_scopes:
        reject.append("ACTION_SCOPE_NOT_ALLOWED")
    if envelope.action_scope in _ACTION_SCOPES_REQUIRING_AUTH and not envelope.authorization_ref:
        hold.append("AUTHORIZATION_REQUIRED")
    for path, expected in (effective_policy.required_value_paths or {}).items():
        if _read_path(envelope.value, path) != expected:
            reject.append(f"HARD_CONSTRAINT_MISMATCH:{path}")
    for path, allowed in (effective_policy.allowed_values_by_path or {}).items():
        if _read_path(envelope.value, path) not in allowed:
            reject.append(f"VALUE_NOT_ALLOWED:{path}")
    if envelope.confidence < effective_policy.min_confidence:
        hold.append("CONFIDENCE_BELOW_THRESHOLD")

    artifacts: list[EvidenceArtifact] = []
    if not envelope.evidence_refs:
        hold.append("EVIDENCE_REFS_MISSING")
    for ref in envelope.evidence_refs:
        artifact = catalog.get(ref)
        if artifact is None:
            hold.append("EVIDENCE_REF_UNKNOWN")
        else:
            artifacts.append(artifact)
            if effective_policy.require_evidence_input_digest_match and artifact.source_digest != envelope.input_digest:
                hold.append("EVIDENCE_INPUT_DIGEST_MISMATCH")
    kinds = {artifact.kind for artifact in artifacts}
    for kind in effective_policy.required_evidence_kinds:
        if kind not in kinds:
            hold.append(f"EVIDENCE_KIND_MISSING:{kind}")

    if reject:
        decision, reasons = "REJECT", reject
    elif hold:
        decision, reasons = "HOLD", hold
    elif envelope.advisory_flags:
        decision, reasons = "ACCEPT_WITH_WARNING", [f"ADVISORY:{flag}" for flag in envelope.advisory_flags]
    else:
        decision, reasons = "ACCEPT", []
    return {
        "decision": decision,
        "accepted": decision in {"ACCEPT", "ACCEPT_WITH_WARNING"},
        "candidate_id": envelope.candidate_id,
        "policy_id": effective_policy.policy_id,
        "reasons": sorted(set(reasons)),
        "evidence_kinds": sorted(kinds),
        "claim_boundary": "Assurance checks declared evidence, constraints, confidence, and action scope only. It does not prove perception, identity, game strategy, or real-world truth.",
    }


def _validate_envelope(envelope: CandidateEnvelope) -> None:
    if not all(isinstance(field, str) and field for field in (envelope.candidate_id, envelope.modality, envelope.claim_type, envelope.producer_id, envelope.input_digest)):
        raise CandidateAssuranceError("INVALID_CANDIDATE_ENVELOPE")
    if not isinstance(envelope.value, dict) or not isinstance(envelope.confidence, (int, float)) or isinstance(envelope.confidence, bool) or not 0 <= envelope.confidence <= 1:
        raise CandidateAssuranceError("INVALID_CANDIDATE_VALUE")
    if not isinstance(envelope.evidence_refs, tuple) or not all(isinstance(ref, str) and ref for ref in envelope.evidence_refs):
        raise CandidateAssuranceError("INVALID_EVIDENCE_REFS")
    if envelope.action_scope not in _ACTION_SCOPES or not isinstance(envelope.authorization_ref, (str, type(None))):
        raise CandidateAssuranceError("INVALID_ACTION_SCOPE")
    if not isinstance(envelope.advisory_flags, tuple) or not all(isinstance(flag, str) and flag for flag in envelope.advisory_flags):
        raise CandidateAssuranceError("INVALID_ADVISORY_FLAGS")


def _validate_policy(policy: CandidateAssurancePolicy) -> None:
    if not isinstance(policy, CandidateAssurancePolicy) or not isinstance(policy.policy_id, str) or not policy.policy_id:
        raise CandidateAssuranceError("INVALID_CANDIDATE_ASSURANCE_POLICY")
    for values, error in ((policy.allowed_modalities, "INVALID_ALLOWED_MODALITIES"), (policy.allowed_claim_types, "INVALID_ALLOWED_CLAIM_TYPES"), (policy.required_evidence_kinds, "INVALID_REQUIRED_EVIDENCE_KINDS")):
        if not isinstance(values, tuple) or not all(isinstance(item, str) and item for item in values):
            raise CandidateAssuranceError(error)
    if not policy.allowed_modalities or not policy.allowed_claim_types or not isinstance(policy.min_confidence, (int, float)) or isinstance(policy.min_confidence, bool) or not 0 <= policy.min_confidence <= 1:
        raise CandidateAssuranceError("INVALID_CANDIDATE_ASSURANCE_POLICY")
    if not isinstance(policy.required_value_paths, (dict, type(None))) or not isinstance(policy.allowed_values_by_path, (dict, type(None))):
        raise CandidateAssuranceError("INVALID_CANDIDATE_ASSURANCE_POLICY")
    if not isinstance(policy.allowed_action_scopes, tuple) or not policy.allowed_action_scopes or not set(policy.allowed_action_scopes).issubset(_ACTION_SCOPES):
        raise CandidateAssuranceError("INVALID_ALLOWED_ACTION_SCOPES")
    if not isinstance(policy.require_evidence_input_digest_match, bool):
        raise CandidateAssuranceError("INVALID_EVIDENCE_INPUT_MATCH_POLICY")


def _normalize_catalog(source: Mapping[str, EvidenceArtifact | Mapping[str, Any]]) -> dict[str, EvidenceArtifact]:
    if not isinstance(source, Mapping):
        raise CandidateAssuranceError("INVALID_EVIDENCE_CATALOG")
    catalog: dict[str, EvidenceArtifact] = {}
    for evidence_id, raw in source.items():
        artifact = raw if isinstance(raw, EvidenceArtifact) else EvidenceArtifact.from_dict(raw)
        if not isinstance(evidence_id, str) or evidence_id != artifact.evidence_id:
            raise CandidateAssuranceError("EVIDENCE_ARTIFACT_ID_MISMATCH")
        catalog[evidence_id] = artifact
    return catalog


def _read_path(value: Mapping[str, Any], path: str) -> Any:
    current: Any = value
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return None
        current = current[segment]
    return current
