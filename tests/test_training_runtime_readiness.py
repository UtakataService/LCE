from lce_validation.runtime.training_runtime_readiness import assess_training_runtime, validate_training_runtime_spec


def _raw():
    return {
        "schema_version": "lce-training-runtime/v1", "spec_id": "pilot", "spec_version": "v1", "require_cuda": True,
        "corpus_path": "corpus.jsonl", "tokenizer_path": "tokenizer.json", "checkpoint_dir": "checkpoints",
        "target_snapshot_hash": "sha256:target", "corpus_snapshot_hash": "sha256:corpus",
    }


def test_readiness_is_go_only_when_runtime_and_artifacts_exist(tmp_path):
    (tmp_path / "corpus.jsonl").write_text("row\n", encoding="utf-8")
    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    spec = validate_training_runtime_spec(_raw(), base_dir=tmp_path)

    result = assess_training_runtime(spec, package_probe=lambda _: True, cuda_probe=lambda: True)

    assert result["ready"]
    assert result["reasons"] == []
    assert result["spec_identity"]["spec_hash"].startswith("sha256:")


def test_readiness_reports_missing_packages_cuda_and_artifacts(tmp_path):
    spec = validate_training_runtime_spec(_raw(), base_dir=tmp_path)

    result = assess_training_runtime(spec, package_probe=lambda _: False, cuda_probe=lambda: False)

    assert not result["ready"]
    assert result["missing_packages"]
    assert {"MISSING_TRAINING_PACKAGES", "CUDA_NOT_AVAILABLE", "CORPUS_ARTIFACT_MISSING", "TOKENIZER_ARTIFACT_MISSING"}.issubset(result["reasons"])
