"""Conservative release gating for a learned model plus LCE control layer."""
from __future__ import annotations

from typing import Any, Mapping

from .experiment_ledger import release_claim_status
from .post_training_contract import PostTrainingManifest
from .quality_target import QualityTarget
from .training_data_contract import CorpusManifest


def evaluate_model_release_gate(
    *,
    target: QualityTarget,
    corpus: CorpusManifest,
    post_training: PostTrainingManifest,
    experiment_records: list[Mapping[str, Any]],
    runtime_profile: Mapping[str, Any],
    adapter_contract_passed: bool,
) -> dict[str, Any]:
    """Return a NO-GO-first decision without making a quality judgement."""
    reasons: list[str] = []
    claim = release_claim_status(target, experiment_records)
    profile = _validate_profile(runtime_profile)
    if profile["target_snapshot_hash"] != target.snapshot_hash:
        reasons.append("TARGET_SNAPSHOT_MISMATCH")
    if profile["corpus_snapshot_hash"] != corpus.snapshot_hash:
        reasons.append("CORPUS_SNAPSHOT_MISMATCH")
    if profile["post_training_snapshot_hash"] != post_training.snapshot_hash:
        reasons.append("POST_TRAINING_SNAPSHOT_MISMATCH")
    if not adapter_contract_passed:
        reasons.append("ADAPTER_CONTRACT_NOT_PASSED")
    if not claim["publishable"]:
        reasons.append("QUALITY_CLAIM_GATE_NOT_SATISFIED")
    if not profile["lce_control_enabled"]:
        reasons.append("LCE_CONTROL_NOT_ENABLED")
    return {
        "decision": "GO" if not reasons else "NO_GO",
        "reasons": sorted(reasons),
        "runtime_profile_id": profile["runtime_profile_id"],
        "claim_status": claim,
        "claim_boundary": "A GO validates declared evidence completeness, not general intelligence, safety completeness, or 20B-class parity.",
    }


def _validate_profile(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"runtime_profile_id", "model_id", "target_snapshot_hash", "corpus_snapshot_hash", "post_training_snapshot_hash", "lce_control_enabled"}
    if not isinstance(value, Mapping) or required - set(value):
        raise ValueError("INVALID_MODEL_RUNTIME_PROFILE")
    if not all(isinstance(value[field], str) and value[field] for field in required - {"lce_control_enabled"}):
        raise ValueError("INVALID_MODEL_RUNTIME_PROFILE")
    if not isinstance(value["lce_control_enabled"], bool):
        raise ValueError("INVALID_MODEL_RUNTIME_PROFILE")
    return dict(value)
