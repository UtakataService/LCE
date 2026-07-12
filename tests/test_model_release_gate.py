from lce_validation.runtime.model_release_gate import evaluate_model_release_gate
from lce_validation.runtime.post_training_contract import load_post_training_manifest
from lce_validation.runtime.quality_target import load_quality_target
from lce_validation.runtime.training_data_contract import load_corpus_manifest


TARGET = load_quality_target("lce_validation/fixtures/lce_20b_quality_target_v1.json")
CORPUS = load_corpus_manifest("lce_validation/fixtures/lce_20b_pilot_corpus_manifest_v1.json")
POST = load_post_training_manifest("lce_validation/fixtures/lce_post_training_manifest_v1.json")


def _profile():
    return {
        "runtime_profile_id": "pilot-profile-v1",
        "model_id": "pilot-100m",
        "target_snapshot_hash": TARGET.snapshot_hash,
        "corpus_snapshot_hash": CORPUS.snapshot_hash,
        "post_training_snapshot_hash": POST.snapshot_hash,
        "lce_control_enabled": True,
    }


def test_release_gate_stays_no_go_without_real_sealed_evidence():
    gate = evaluate_model_release_gate(target=TARGET, corpus=CORPUS, post_training=POST, experiment_records=[], runtime_profile=_profile(), adapter_contract_passed=True)

    assert gate["decision"] == "NO_GO"
    assert gate["reasons"] == ["QUALITY_CLAIM_GATE_NOT_SATISFIED"]


def test_release_gate_detects_profile_provenance_drift():
    profile = _profile()
    profile["corpus_snapshot_hash"] = "sha256:other"
    gate = evaluate_model_release_gate(target=TARGET, corpus=CORPUS, post_training=POST, experiment_records=[], runtime_profile=profile, adapter_contract_passed=False)

    assert gate["decision"] == "NO_GO"
    assert "CORPUS_SNAPSHOT_MISMATCH" in gate["reasons"]
    assert "ADAPTER_CONTRACT_NOT_PASSED" in gate["reasons"]
