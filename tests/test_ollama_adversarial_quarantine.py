from lce_validation.runtime.ollama_adversarial_quarantine import generate_adversarial_candidate


def test_adversarial_candidate_is_quarantined_and_has_no_gold():
    candidate = generate_adversarial_candidate(
        model_id="gemma4:12b", model_digest="sha256:model", target_tag="topic_shift",
        request_fn=lambda _: {"response": '{"input_text":"Before that, can we discuss a different subject?","phenomenon_tags":["topic_shift"]}'},
    )
    assert candidate["status"] == "QUARANTINED"
    assert "HUMAN_GOLD_REQUIRED" in candidate["review_flags"]
