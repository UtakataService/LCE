"""Evidence-backed 'wait a moment' gate for already accepted results.

This module does not infer that an accepted result is wrong.  It turns declared
contradictions, thin evidence, near-boundary scores, and unresolved cross-checks
into auditable pause decisions before an accepted result is promoted or acted on.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class AcceptanceChallengeError(ValueError):
    pass


_SIGNAL_CATEGORIES = {
    "contradiction",
    "evidence_gap",
    "near_boundary",
    "cross_check_failure",
    "unresolved_advisory",
    "recent_regression",
    "outlier",
    "independence_collision",
}


@dataclass(frozen=True, slots=True)
class ChallengeSignal:
    signal_id: str
    category: str
    severity: float
    source_key: str
    status: str = "open"
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AcceptedResult:
    result_id: str
    decision: str
    evidence_refs: tuple[str, ...]
    reviewer_keys: tuple[str, ...] = ()
    score: float | None = None
    acceptance_threshold: float | None = None
    cross_checks: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class AcceptanceChallengePolicy:
    policy_id: str
    accepted_decisions: tuple[str, ...] = ("ACCEPT", "pass", "approved")
    min_evidence_refs: int = 1
    min_independent_reviewers: int = 1
    min_score_margin: float | None = None
    required_cross_checks: tuple[str, ...] = ()
    challenge_severity: float = 0.4
    block_severity: float = 0.8

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AcceptanceChallengePolicy":
        if not isinstance(value, Mapping):
            raise AcceptanceChallengeError("INVALID_ACCEPTANCE_CHALLENGE_POLICY")
        policy = cls(
            policy_id=value.get("policy_id", ""),
            accepted_decisions=tuple(value.get("accepted_decisions", ("ACCEPT", "pass", "approved"))),
            min_evidence_refs=value.get("min_evidence_refs", 1),
            min_independent_reviewers=value.get("min_independent_reviewers", 1),
            min_score_margin=value.get("min_score_margin"),
            required_cross_checks=tuple(value.get("required_cross_checks", ())),
            challenge_severity=value.get("challenge_severity", 0.4),
            block_severity=value.get("block_severity", 0.8),
        )
        _validate_policy(policy)
        return policy


def challenge_accepted_result(
    result: AcceptedResult | Mapping[str, Any],
    policy: AcceptanceChallengePolicy | Mapping[str, Any],
    evidence_catalog: Mapping[str, Mapping[str, Any]],
    signals: list[ChallengeSignal | Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Return ``CLEAR``, ``CHALLENGE``, or ``BLOCK`` for an accepted result."""
    accepted = result if isinstance(result, AcceptedResult) else _result_from_dict(result)
    effective_policy = policy if isinstance(policy, AcceptanceChallengePolicy) else AcceptanceChallengePolicy.from_dict(policy)
    catalog = _normalize_catalog(evidence_catalog)
    normalized_signals = tuple(signal if isinstance(signal, ChallengeSignal) else _signal_from_dict(signal) for signal in signals)
    if accepted.decision not in effective_policy.accepted_decisions:
        raise AcceptanceChallengeError("RESULT_NOT_ACCEPTED")

    challenge: list[str] = []
    block: list[str] = []
    known_evidence = [ref for ref in accepted.evidence_refs if ref in catalog]
    if len(accepted.evidence_refs) < effective_policy.min_evidence_refs:
        challenge.append("ACCEPTANCE_EVIDENCE_COUNT_BELOW_POLICY")
    if len(known_evidence) != len(accepted.evidence_refs):
        challenge.append("ACCEPTANCE_EVIDENCE_REF_UNKNOWN")
    independent_count = len(set(accepted.reviewer_keys))
    if independent_count < effective_policy.min_independent_reviewers:
        challenge.append("INDEPENDENT_REVIEWER_COUNT_BELOW_POLICY")
    if effective_policy.min_score_margin is not None:
        if accepted.score is None or accepted.acceptance_threshold is None:
            challenge.append("SCORE_MARGIN_UNAVAILABLE")
        elif accepted.score - accepted.acceptance_threshold < effective_policy.min_score_margin:
            challenge.append("SCORE_NEAR_ACCEPTANCE_BOUNDARY")
    for check in effective_policy.required_cross_checks:
        status = (accepted.cross_checks or {}).get(check)
        if status == "fail":
            block.append(f"CROSS_CHECK_FAILED:{check}")
        elif status != "pass":
            challenge.append(f"CROSS_CHECK_UNRESOLVED:{check}")

    active_signals: list[dict[str, Any]] = []
    for signal in normalized_signals:
        if signal.status == "resolved":
            continue
        active_signals.append({"signal_id": signal.signal_id, "category": signal.category, "severity": signal.severity, "source_key": signal.source_key})
        if signal.category in {"contradiction", "cross_check_failure"} and signal.severity >= effective_policy.block_severity:
            block.append(f"SIGNAL_BLOCK:{signal.category}:{signal.signal_id}")
        elif signal.severity >= effective_policy.challenge_severity:
            challenge.append(f"SIGNAL_CHALLENGE:{signal.category}:{signal.signal_id}")

    if block:
        decision, reasons = "BLOCK", block + challenge
    elif challenge:
        decision, reasons = "CHALLENGE", challenge
    else:
        decision, reasons = "CLEAR", []
    return {
        "decision": decision,
        "should_pause": decision in {"CHALLENGE", "BLOCK"},
        "result_id": accepted.result_id,
        "policy_id": effective_policy.policy_id,
        "independent_reviewer_count": independent_count,
        "active_signals": active_signals,
        "reasons": sorted(set(reasons)),
        "claim_boundary": "Checks declared review evidence, margins, cross-check state, and challenge signals only. It does not establish that an accepted result is semantically wrong, unsafe, unfair, or low quality.",
    }


def _result_from_dict(value: Mapping[str, Any]) -> AcceptedResult:
    if not isinstance(value, Mapping):
        raise AcceptanceChallengeError("INVALID_ACCEPTED_RESULT")
    cross_checks = value.get("cross_checks")
    item = AcceptedResult(
        result_id=value.get("result_id", ""),
        decision=value.get("decision", ""),
        evidence_refs=tuple(value.get("evidence_refs", ())),
        reviewer_keys=tuple(value.get("reviewer_keys", ())),
        score=value.get("score"),
        acceptance_threshold=value.get("acceptance_threshold"),
        cross_checks=dict(cross_checks) if isinstance(cross_checks, Mapping) else cross_checks,
    )
    if not isinstance(item.result_id, str) or not item.result_id or not isinstance(item.decision, str) or not item.decision:
        raise AcceptanceChallengeError("INVALID_ACCEPTED_RESULT")
    if not all(isinstance(ref, str) and ref for ref in item.evidence_refs) or not all(isinstance(key, str) and key for key in item.reviewer_keys):
        raise AcceptanceChallengeError("INVALID_ACCEPTED_RESULT")
    if any(value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)) for value in (item.score, item.acceptance_threshold)):
        raise AcceptanceChallengeError("INVALID_ACCEPTED_RESULT")
    if item.cross_checks is not None and (not all(isinstance(key, str) and key and state in {"pass", "fail", "unknown"} for key, state in item.cross_checks.items())):
        raise AcceptanceChallengeError("INVALID_CROSS_CHECKS")
    return item


def _signal_from_dict(value: Mapping[str, Any]) -> ChallengeSignal:
    if not isinstance(value, Mapping):
        raise AcceptanceChallengeError("INVALID_CHALLENGE_SIGNAL")
    signal = ChallengeSignal(value.get("signal_id", ""), value.get("category", ""), value.get("severity"), value.get("source_key", ""), value.get("status", "open"), tuple(value.get("evidence_refs", ())))
    if not isinstance(signal.signal_id, str) or not signal.signal_id or signal.category not in _SIGNAL_CATEGORIES or not isinstance(signal.severity, (int, float)) or isinstance(signal.severity, bool) or not 0 <= signal.severity <= 1 or not isinstance(signal.source_key, str) or not signal.source_key or signal.status not in {"open", "resolved"} or not all(isinstance(ref, str) and ref for ref in signal.evidence_refs):
        raise AcceptanceChallengeError("INVALID_CHALLENGE_SIGNAL")
    return signal


def _normalize_catalog(source: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if not isinstance(source, Mapping):
        raise AcceptanceChallengeError("INVALID_ACCEPTANCE_EVIDENCE_CATALOG")
    result: dict[str, Mapping[str, Any]] = {}
    for evidence_id, evidence in source.items():
        if not isinstance(evidence_id, str) or not evidence_id or not isinstance(evidence, Mapping):
            raise AcceptanceChallengeError("INVALID_ACCEPTANCE_EVIDENCE_CATALOG")
        result[evidence_id] = evidence
    return result


def _validate_policy(policy: AcceptanceChallengePolicy) -> None:
    if not isinstance(policy.policy_id, str) or not policy.policy_id or not all(isinstance(item, str) and item for item in policy.accepted_decisions):
        raise AcceptanceChallengeError("INVALID_ACCEPTANCE_CHALLENGE_POLICY")
    if not isinstance(policy.min_evidence_refs, int) or not isinstance(policy.min_independent_reviewers, int) or policy.min_evidence_refs < 0 or policy.min_independent_reviewers < 0:
        raise AcceptanceChallengeError("INVALID_ACCEPTANCE_CHALLENGE_POLICY")
    if policy.min_score_margin is not None and (not isinstance(policy.min_score_margin, (int, float)) or isinstance(policy.min_score_margin, bool) or policy.min_score_margin < 0):
        raise AcceptanceChallengeError("INVALID_ACCEPTANCE_CHALLENGE_POLICY")
    if not all(isinstance(check, str) and check for check in policy.required_cross_checks):
        raise AcceptanceChallengeError("INVALID_ACCEPTANCE_CHALLENGE_POLICY")
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1 for value in (policy.challenge_severity, policy.block_severity)) or policy.challenge_severity > policy.block_severity:
        raise AcceptanceChallengeError("INVALID_ACCEPTANCE_CHALLENGE_POLICY")
