import json

import pytest

from lce_validation.runtime.ollama_teacher_quarantine import TeacherCandidateError, append_quarantined_candidate, generate_teacher_candidate


def _response(payload):
    return {"response": json.dumps({"input_variant": "Could you clarify the goal?", "candidate_response": "Could you share the goal and constraints?", "claim_uses": [], "review_flags": ["LOW_RISK"]})}


def test_teacher_candidate_is_always_quarantined_and_provenanced(tmp_path):
    record = generate_teacher_candidate(model_id="gemma4:12b", model_digest="sha256:model", seed_id="seed-1", seed_text="Please clarify.", language="en", request_fn=_response)
    append_quarantined_candidate(tmp_path / "candidates.jsonl", record)

    assert record["status"] == "QUARANTINED"
    assert "HUMAN_REVIEW_REQUIRED" in record["review_flags"]
    assert (tmp_path / "candidates.jsonl").read_text(encoding="utf-8")


def test_teacher_candidate_with_claim_use_is_rejected():
    with pytest.raises(TeacherCandidateError, match="UNSAFE_TEACHER_CANDIDATE"):
        generate_teacher_candidate(
            model_id="gemma4:12b", model_digest="sha256:model", seed_id="seed-1", seed_text="Please clarify.", language="en",
            request_fn=lambda _: {"response": '{"input_variant":"x","candidate_response":"y","claim_uses":["fact_assertion"],"review_flags":[]}'},
        )
