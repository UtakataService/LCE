"""Rubric-backed audit for externally produced grading records.

The gateway verifies whether declared scores obey a declared rubric, evidence,
calibration and independence policy.  It does not independently judge the
semantic quality of a submitted answer or replace a human/domain grader.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class GradingAssuranceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RubricCriterion:
    criterion_id: str
    max_points: float
    required_evidence_kinds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CriterionScore:
    criterion_id: str
    points: float
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GradingRecord:
    grading_id: str
    rubric_id: str
    grader_id: str
    independence_key: str
    calibration_id: str | None
    criterion_scores: tuple[CriterionScore, ...]
    total_score: float
    verdict: str


@dataclass(frozen=True, slots=True)
class GradingAssurancePolicy:
    policy_id: str
    rubric_id: str
    criteria: tuple[RubricCriterion, ...]
    allowed_verdicts: tuple[str, ...] = ("pass", "fail")
    min_grader_count: int = 1
    min_independent_graders: int = 1
    max_total_score_spread: float | None = None
    require_calibration: bool = False
    accepted_calibration_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GradingAssurancePolicy":
        if not isinstance(value, Mapping):
            raise GradingAssuranceError("INVALID_GRADING_ASSURANCE_POLICY")
        raw_criteria = value.get("criteria")
        if not isinstance(raw_criteria, list):
            raise GradingAssuranceError("INVALID_RUBRIC_CRITERIA")
        criteria = tuple(_criterion_from_dict(item) for item in raw_criteria)
        policy = cls(
            policy_id=value.get("policy_id", ""),
            rubric_id=value.get("rubric_id", ""),
            criteria=criteria,
            allowed_verdicts=tuple(value.get("allowed_verdicts", ("pass", "fail"))),
            min_grader_count=value.get("min_grader_count", 1),
            min_independent_graders=value.get("min_independent_graders", 1),
            max_total_score_spread=value.get("max_total_score_spread"),
            require_calibration=value.get("require_calibration", False),
            accepted_calibration_ids=tuple(value.get("accepted_calibration_ids", ())),
        )
        _validate_policy(policy)
        return policy


def audit_grading_records(
    records: list[GradingRecord | Mapping[str, Any]],
    policy: GradingAssurancePolicy | Mapping[str, Any],
    evidence_catalog: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Audit declared grading records and return ACCEPT/HOLD/REJECT.

    ``REJECT`` is a hard contract violation; ``HOLD`` means that a valid
    conclusion cannot yet be accepted without more evidence, calibration, or
    independent adjudication.
    """
    effective_policy = policy if isinstance(policy, GradingAssurancePolicy) else GradingAssurancePolicy.from_dict(policy)
    normalized_records = tuple(record if isinstance(record, GradingRecord) else _record_from_dict(record) for record in records)
    catalog = _normalize_evidence_catalog(evidence_catalog)
    if not normalized_records:
        raise GradingAssuranceError("GRADING_RECORDS_REQUIRED")

    reject: list[str] = []
    hold: list[str] = []
    criterion_by_id = {criterion.criterion_id: criterion for criterion in effective_policy.criteria}
    per_record: list[dict[str, Any]] = []
    for record in normalized_records:
        record_reject, record_hold = _audit_record(record, effective_policy, criterion_by_id, catalog)
        reject.extend(record_reject)
        hold.extend(record_hold)
        per_record.append({
            "grading_id": record.grading_id,
            "grader_id": record.grader_id,
            "total_score": record.total_score,
            "verdict": record.verdict,
            "reject_reasons": sorted(set(record_reject)),
            "hold_reasons": sorted(set(record_hold)),
        })

    if len(normalized_records) < effective_policy.min_grader_count:
        hold.append("GRADER_COUNT_BELOW_POLICY")
    independent_count = len({record.independence_key for record in normalized_records})
    if independent_count < effective_policy.min_independent_graders:
        hold.append("INDEPENDENT_GRADER_COUNT_BELOW_POLICY")
    if effective_policy.max_total_score_spread is not None:
        totals = [record.total_score for record in normalized_records]
        if max(totals) - min(totals) > effective_policy.max_total_score_spread:
            hold.append("TOTAL_SCORE_DISAGREEMENT_REQUIRES_ADJUDICATION")
    if len({record.verdict for record in normalized_records}) > 1:
        hold.append("VERDICT_DISAGREEMENT_REQUIRES_ADJUDICATION")

    if reject:
        decision, reasons = "REJECT", reject
    elif hold:
        decision, reasons = "HOLD", hold
    else:
        decision, reasons = "ACCEPT", []
    return {
        "decision": decision,
        "accepted": decision == "ACCEPT",
        "policy_id": effective_policy.policy_id,
        "rubric_id": effective_policy.rubric_id,
        "grader_count": len(normalized_records),
        "independent_grader_count": independent_count,
        "records": per_record,
        "reasons": sorted(set(reasons)),
        "claim_boundary": "Checks declared rubric coverage, score arithmetic, evidence references, calibration and multi-grader agreement only. It does not independently evaluate answer quality, correctness, fairness, or grader competence.",
    }


def _audit_record(record: GradingRecord, policy: GradingAssurancePolicy, criteria: Mapping[str, RubricCriterion], catalog: Mapping[str, str]) -> tuple[list[str], list[str]]:
    reject: list[str] = []
    hold: list[str] = []
    if record.rubric_id != policy.rubric_id:
        reject.append("RUBRIC_ID_MISMATCH")
    if record.verdict not in policy.allowed_verdicts:
        reject.append("VERDICT_NOT_ALLOWED")
    if policy.require_calibration:
        if not record.calibration_id:
            hold.append("CALIBRATION_REQUIRED")
        elif policy.accepted_calibration_ids and record.calibration_id not in policy.accepted_calibration_ids:
            hold.append("CALIBRATION_NOT_ACCEPTED")
    seen: set[str] = set()
    score_total = 0.0
    for score in record.criterion_scores:
        criterion = criteria.get(score.criterion_id)
        if criterion is None:
            reject.append(f"CRITERION_NOT_IN_RUBRIC:{score.criterion_id}")
            continue
        if score.criterion_id in seen:
            reject.append(f"CRITERION_DUPLICATED:{score.criterion_id}")
            continue
        seen.add(score.criterion_id)
        if not 0 <= score.points <= criterion.max_points:
            reject.append(f"CRITERION_POINTS_OUT_OF_RANGE:{score.criterion_id}")
        score_total += score.points
        kinds = {catalog[ref] for ref in score.evidence_refs if ref in catalog}
        if len(kinds) != len(score.evidence_refs):
            hold.append(f"EVIDENCE_REF_UNKNOWN:{score.criterion_id}")
        for kind in criterion.required_evidence_kinds:
            if kind not in kinds:
                hold.append(f"EVIDENCE_KIND_MISSING:{score.criterion_id}:{kind}")
    for criterion_id in criteria:
        if criterion_id not in seen:
            reject.append(f"RUBRIC_CRITERION_MISSING:{criterion_id}")
    if abs(score_total - record.total_score) > 1e-9:
        reject.append("TOTAL_SCORE_ARITHMETIC_MISMATCH")
    return reject, hold


def _criterion_from_dict(value: Mapping[str, Any]) -> RubricCriterion:
    if not isinstance(value, Mapping):
        raise GradingAssuranceError("INVALID_RUBRIC_CRITERION")
    criterion = RubricCriterion(
        criterion_id=value.get("criterion_id", ""),
        max_points=value.get("max_points"),
        required_evidence_kinds=tuple(value.get("required_evidence_kinds", ())),
    )
    if not isinstance(criterion.criterion_id, str) or not criterion.criterion_id or not isinstance(criterion.max_points, (int, float)) or isinstance(criterion.max_points, bool) or criterion.max_points < 0 or not all(isinstance(item, str) and item for item in criterion.required_evidence_kinds):
        raise GradingAssuranceError("INVALID_RUBRIC_CRITERION")
    return criterion


def _record_from_dict(value: Mapping[str, Any]) -> GradingRecord:
    if not isinstance(value, Mapping) or not isinstance(value.get("criterion_scores"), list):
        raise GradingAssuranceError("INVALID_GRADING_RECORD")
    scores: list[CriterionScore] = []
    for score in value["criterion_scores"]:
        if not isinstance(score, Mapping):
            raise GradingAssuranceError("INVALID_CRITERION_SCORE")
        item = CriterionScore(score.get("criterion_id", ""), score.get("points"), tuple(score.get("evidence_refs", ())))
        if not isinstance(item.criterion_id, str) or not item.criterion_id or not isinstance(item.points, (int, float)) or isinstance(item.points, bool) or not all(isinstance(ref, str) and ref for ref in item.evidence_refs):
            raise GradingAssuranceError("INVALID_CRITERION_SCORE")
        scores.append(item)
    record = GradingRecord(value.get("grading_id", ""), value.get("rubric_id", ""), value.get("grader_id", ""), value.get("independence_key", ""), value.get("calibration_id"), tuple(scores), value.get("total_score"), value.get("verdict", ""))
    if not all(isinstance(field, str) and field for field in (record.grading_id, record.rubric_id, record.grader_id, record.independence_key, record.verdict)) or not isinstance(record.calibration_id, (str, type(None))) or not isinstance(record.total_score, (int, float)) or isinstance(record.total_score, bool):
        raise GradingAssuranceError("INVALID_GRADING_RECORD")
    return record


def _normalize_evidence_catalog(source: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    if not isinstance(source, Mapping):
        raise GradingAssuranceError("INVALID_GRADING_EVIDENCE_CATALOG")
    result: dict[str, str] = {}
    for evidence_id, item in source.items():
        if not isinstance(evidence_id, str) or not evidence_id or not isinstance(item, Mapping) or not isinstance(item.get("kind"), str) or not item["kind"]:
            raise GradingAssuranceError("INVALID_GRADING_EVIDENCE_CATALOG")
        result[evidence_id] = item["kind"]
    return result


def _validate_policy(policy: GradingAssurancePolicy) -> None:
    if not isinstance(policy.policy_id, str) or not policy.policy_id or not isinstance(policy.rubric_id, str) or not policy.rubric_id or not policy.criteria:
        raise GradingAssuranceError("INVALID_GRADING_ASSURANCE_POLICY")
    ids = [criterion.criterion_id for criterion in policy.criteria]
    if len(ids) != len(set(ids)) or not all(isinstance(item, str) and item for item in policy.allowed_verdicts):
        raise GradingAssuranceError("INVALID_GRADING_ASSURANCE_POLICY")
    if not isinstance(policy.min_grader_count, int) or not isinstance(policy.min_independent_graders, int) or policy.min_grader_count < 1 or policy.min_independent_graders < 1:
        raise GradingAssuranceError("INVALID_GRADING_ASSURANCE_POLICY")
    if policy.max_total_score_spread is not None and (not isinstance(policy.max_total_score_spread, (int, float)) or isinstance(policy.max_total_score_spread, bool) or policy.max_total_score_spread < 0):
        raise GradingAssuranceError("INVALID_GRADING_ASSURANCE_POLICY")
    if not isinstance(policy.require_calibration, bool) or not all(isinstance(item, str) and item for item in policy.accepted_calibration_ids):
        raise GradingAssuranceError("INVALID_GRADING_ASSURANCE_POLICY")
