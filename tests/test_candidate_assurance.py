import pytest

from lce_validation.runtime.candidate_assurance import CandidateAssuranceError, assess_candidate


def _artifact(evidence_id, kind):
    return {"evidence_id": evidence_id, "kind": kind, "source_digest": f"sha256:{evidence_id}"}


def _video_policy(**overrides):
    value = {
        "policy_id": "video-object-v1",
        "allowed_modalities": ["video"],
        "allowed_claim_types": ["object_presence"],
        "min_confidence": 0.8,
        "required_evidence_kinds": ["video_frame", "track"],
        "required_value_paths": {"object_id": "vehicle"},
        "allowed_action_scopes": ["display", "persist"],
    }
    value.update(overrides)
    return value


def _candidate(**overrides):
    value = {
        "candidate_id": "candidate-1",
        "modality": "video",
        "claim_type": "object_presence",
        "value": {"object_id": "vehicle"},
        "confidence": 0.9,
        "evidence_refs": ["frame-1", "track-1"],
        "producer_id": "detector-v1",
        "input_digest": "sha256:input",
        "action_scope": "display",
    }
    value.update(overrides)
    return value


def _catalog():
    return {"frame-1": _artifact("frame-1", "video_frame"), "track-1": _artifact("track-1", "track")}


def test_video_object_candidate_accepts_with_required_artifacts():
    result = assess_candidate(_candidate(), _video_policy(), _catalog())
    assert result["decision"] == "ACCEPT"


def test_low_confidence_or_missing_audio_evidence_holds_instead_of_rejecting():
    policy = {
        "policy_id": "audio-speaker-v1",
        "allowed_modalities": ["audio"],
        "allowed_claim_types": ["speaker_phrase"],
        "min_confidence": 0.9,
        "required_evidence_kinds": ["audio_segment", "speaker_embedding", "transcript"],
        "allowed_action_scopes": ["display"],
    }
    candidate = _candidate(
        modality="audio", claim_type="speaker_phrase", confidence=0.6,
        evidence_refs=["segment", "embedding"], value={"speaker_id": "alice", "phrase": "open"},
    )
    result = assess_candidate(candidate, policy, {"segment": _artifact("segment", "audio_segment"), "embedding": _artifact("embedding", "speaker_embedding")})
    assert result["decision"] == "HOLD"
    assert "CONFIDENCE_BELOW_THRESHOLD" in result["reasons"]
    assert "EVIDENCE_KIND_MISSING:transcript" in result["reasons"]


def test_illegal_game_move_is_rejected_but_advisory_theory_is_only_a_warning():
    policy = {
        "policy_id": "shogi-move-v1",
        "allowed_modalities": ["rule_engine"],
        "allowed_claim_types": ["board_move"],
        "required_value_paths": {"game": "shogi", "legal": True},
        "required_evidence_kinds": ["board_state"],
        "allowed_action_scopes": ["display", "state_commit"],
    }
    illegal = _candidate(modality="rule_engine", claim_type="board_move", value={"game": "shogi", "legal": False}, evidence_refs=["board"], action_scope="display")
    assert assess_candidate(illegal, policy, {"board": _artifact("board", "board_state")})["decision"] == "REJECT"
    advisory = _candidate(modality="rule_engine", claim_type="board_move", value={"game": "shogi", "legal": True}, evidence_refs=["board"], advisory_flags=["theory_outside_opening_book"])
    assert assess_candidate(advisory, policy, {"board": _artifact("board", "board_state")})["decision"] == "ACCEPT_WITH_WARNING"


def test_npc_action_scope_rejects_unpermitted_action_and_holds_without_authorization():
    policy = {
        "policy_id": "npc-v1",
        "allowed_modalities": ["game"],
        "allowed_claim_types": ["npc_action"],
        "required_value_paths": {"permitted": True},
        "allowed_values_by_path": {"action": ["move", "speak"], "zone": ["village"]},
        "required_evidence_kinds": ["world_state"],
        "allowed_action_scopes": ["display", "state_commit"],
    }
    denied = _candidate(modality="game", claim_type="npc_action", value={"permitted": False, "action": "move", "zone": "village"}, evidence_refs=["world"], action_scope="display")
    assert assess_candidate(denied, policy, {"world": _artifact("world", "world_state")})["decision"] == "REJECT"
    unapproved = _candidate(modality="game", claim_type="npc_action", value={"permitted": True, "action": "move", "zone": "village"}, evidence_refs=["world"], action_scope="state_commit")
    assert assess_candidate(unapproved, policy, {"world": _artifact("world", "world_state")})["decision"] == "HOLD"


def test_invalid_envelope_is_not_silently_assessed():
    with pytest.raises(CandidateAssuranceError, match="INVALID_CANDIDATE_VALUE"):
        assess_candidate(_candidate(confidence=1.5), _video_policy(), _catalog())


def test_provenance_mismatch_holds_when_policy_requires_same_input_digest():
    result = assess_candidate(
        _candidate(input_digest="sha256:video-a"),
        _video_policy(require_evidence_input_digest_match=True),
        _catalog(),
    )
    assert result["decision"] == "HOLD"
    assert "EVIDENCE_INPUT_DIGEST_MISMATCH" in result["reasons"]
