import pytest

from lce_validation.runtime.acceptance_challenge import AcceptanceChallengeError, challenge_accepted_result


def _policy(**overrides):
    value = {"policy_id": "promotion-v1", "min_evidence_refs": 1, "min_independent_reviewers": 2, "min_score_margin": 0.1, "required_cross_checks": ["schema", "regression"], "challenge_severity": 0.4, "block_severity": 0.8}
    value.update(overrides)
    return value


def _result(**overrides):
    value = {"result_id": "r1", "decision": "ACCEPT", "evidence_refs": ["ev1"], "reviewer_keys": ["team-a", "team-b"], "score": 0.95, "acceptance_threshold": 0.8, "cross_checks": {"schema": "pass", "regression": "pass"}}
    value.update(overrides)
    return value


def test_clear_requires_sufficient_evidence_margin_and_cross_checks():
    result = challenge_accepted_result(_result(), _policy(), {"ev1": {"kind": "trace"}})
    assert result["decision"] == "CLEAR"
    assert not result["should_pause"]


def test_near_boundary_or_thin_evidence_challenges_an_accepted_result():
    result = challenge_accepted_result(_result(score=0.85, reviewer_keys=["team-a"], evidence_refs=[]), _policy(), {})
    assert result["decision"] == "CHALLENGE"
    assert "SCORE_NEAR_ACCEPTANCE_BOUNDARY" in result["reasons"]
    assert "ACCEPTANCE_EVIDENCE_COUNT_BELOW_POLICY" in result["reasons"]
    assert "INDEPENDENT_REVIEWER_COUNT_BELOW_POLICY" in result["reasons"]


def test_open_contradiction_or_failed_cross_check_blocks_promotion():
    contradiction = [{"signal_id": "s1", "category": "contradiction", "severity": 0.9, "source_key": "independent-check", "evidence_refs": ["ev1"]}]
    result = challenge_accepted_result(_result(), _policy(), {"ev1": {"kind": "trace"}}, contradiction)
    assert result["decision"] == "BLOCK"
    assert "SIGNAL_BLOCK:contradiction:s1" in result["reasons"]
    failed = challenge_accepted_result(_result(cross_checks={"schema": "pass", "regression": "fail"}), _policy(), {"ev1": {"kind": "trace"}})
    assert "CROSS_CHECK_FAILED:regression" in failed["reasons"]


def test_nonfatal_open_signal_challenges_and_resolved_signal_does_not():
    open_signal = [{"signal_id": "s2", "category": "recent_regression", "severity": 0.5, "source_key": "ledger"}]
    assert challenge_accepted_result(_result(), _policy(), {"ev1": {"kind": "trace"}}, open_signal)["decision"] == "CHALLENGE"
    resolved = [{"signal_id": "s2", "category": "recent_regression", "severity": 0.9, "source_key": "ledger", "status": "resolved"}]
    assert challenge_accepted_result(_result(), _policy(), {"ev1": {"kind": "trace"}}, resolved)["decision"] == "CLEAR"


def test_nonaccepted_result_or_invalid_signal_is_not_silently_challenged():
    with pytest.raises(AcceptanceChallengeError, match="RESULT_NOT_ACCEPTED"):
        challenge_accepted_result(_result(decision="REJECT"), _policy(), {"ev1": {}})
    with pytest.raises(AcceptanceChallengeError, match="INVALID_CHALLENGE_SIGNAL"):
        challenge_accepted_result(_result(), _policy(), {"ev1": {}}, [{"signal_id": "bad", "category": "unknown", "severity": 1, "source_key": "x"}])
