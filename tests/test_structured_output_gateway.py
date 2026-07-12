from lce_validation.runtime.structured_output_gateway import (
    StructuredOutputContract,
    build_structured_output_instruction,
    process_structured_output,
)


def _contract(**overrides):
    base = {
        "contract_id": "answer-v1",
        "schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string", "minLength": 1},
                "certainty": {"type": "string", "enum": ["known", "uncertain"]},
                "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            },
            "required": ["answer", "certainty"],
            "additionalProperties": False,
        },
        "defaults": {"tags": []},
    }
    base.update(overrides)
    return StructuredOutputContract(**base)


def test_non_structured_model_can_receive_a_json_only_instruction():
    instruction = build_structured_output_instruction("Give a short answer.", _contract())
    assert "exactly one JSON value" in instruction
    assert "answer-v1" in instruction


def test_valid_json_is_accepted_and_optional_safe_default_is_applied():
    result = process_structured_output('{"answer":"Ready","certainty":"known"}', _contract())
    assert result["status"] == "ACCEPTED"
    assert result["value"] == {"answer": "Ready", "certainty": "known", "tags": []}


def test_fenced_json_from_a_non_json_mode_model_is_supported_when_enabled():
    result = process_structured_output('```json\n{"answer":"Ready","certainty":"uncertain"}\n```', _contract())
    assert result["accepted"]


def test_invalid_output_is_returned_for_retry_when_no_repair_adapter_exists():
    result = process_structured_output('{"answer":"Ready"}', _contract())
    assert result["status"] == "RETRY_REQUIRED"
    assert "$.certainty:REQUIRED_PROPERTY_MISSING" in result["violations"]
    assert "PREVIOUS_OUTPUT" in result["repair_instruction"]


def test_lce_can_repair_and_revalidate_one_candidate():
    captured = []

    def repair(prompt):
        captured.append(prompt)
        return '{"answer":"Repaired","certainty":"uncertain"}'

    result = process_structured_output('{"answer":"Broken"}', _contract(), repair_fn=repair, user_request="Return an answer.")
    assert result["status"] == "REPAIRED"
    assert result["value"]["answer"] == "Repaired"
    assert len(captured) == 1


def test_repair_retains_context_and_evidence_summaries():
    captured = []
    result = process_structured_output(
        '{"answer":"Broken"}',
        _contract(),
        repair_fn=lambda prompt: captured.append(prompt) or '{"answer":"Repaired","certainty":"uncertain"}',
        user_request="Return an answer.",
        repair_context_summary="Budget is fixed.",
        repair_evidence_summary="evidence.budget.fixed supports the limit.",
    )
    assert result["status"] == "REPAIRED"
    assert "LCE_CONTEXT_SUMMARY=Budget is fixed." in captured[0]
    assert "LCE_EVIDENCE_SUMMARY=evidence.budget.fixed supports the limit." in captured[0]


def test_failed_repair_is_rejected_without_partial_value():
    result = process_structured_output('{"answer":"Broken"}', _contract(), repair_fn=lambda _: "still prose")
    assert result["status"] == "REJECTED"
    assert result["value"] is None
    assert result["violations"] == ["INVALID_JSON_OUTPUT"]


def test_undeclared_fields_are_rejected():
    result = process_structured_output('{"answer":"Ready","certainty":"known","admin":true}', _contract())
    assert result["status"] == "RETRY_REQUIRED"
    assert "$.admin:UNDECLARED_PROPERTY" in result["violations"]
