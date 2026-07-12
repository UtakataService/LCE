from lce_validation.runtime.controlled_generation import GenerationRequest, execute_controlled_generation
from lce_validation.runtime.ollama_adapter import OllamaControlledAdapter, OllamaOutputProfile, OllamaStructuredOutputAdapter
from lce_validation.runtime.structured_assurance import EvidenceClaim, StructuredAssurancePolicy
from lce_validation.runtime.structured_output_gateway import StructuredOutputContract


def _request():
    return GenerationRequest(
        request_id="req", prompt="Please explain carefully.", plan={"plan_id": "plan"},
        envelope={"allowed_response_steps": ["clarify"], "prohibited_uses": ["fact_assertion"], "required_markers": ["uncertainty_boundary"]},
    )


def test_ollama_adapter_sends_structural_contract_and_returns_json_candidate():
    captured = {}

    def fake(endpoint, payload, timeout):
        captured.update(payload)
        return {"response": '{"text":"Could you add context?","response_step":"clarify","claim_uses":[],"markers":["uncertainty_boundary"]}'}

    adapter = OllamaControlledAdapter("gemma4:12b", request_fn=fake)
    result = execute_controlled_generation(adapter, _request())

    assert result["accepted"]
    assert captured["format"] == "json"
    assert captured["think"] is False
    assert "prohibited_claim_uses" in captured["prompt"]


def test_ollama_adapter_candidate_still_goes_through_lce_rejection():
    adapter = OllamaControlledAdapter(
        "gemma4:12b",
        request_fn=lambda *_: {"response": '{"text":"A fact.","response_step":"clarify","claim_uses":["fact_assertion"],"markers":["uncertainty_boundary"]}'},
    )

    result = execute_controlled_generation(adapter, _request())

    assert not result["accepted"]
    assert result["violations"] == ["PROHIBITED_CLAIM_USE"]


def _structured_contract():
    return StructuredOutputContract(
        contract_id="brief-v1",
        schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}, "certainty": {"type": "string", "enum": ["known", "uncertain"]}},
            "required": ["summary", "certainty"],
            "additionalProperties": False,
        },
    )


def test_non_structured_ollama_output_is_repaired_by_the_lce_gateway():
    calls = []

    def fake(_, payload, __):
        calls.append(payload)
        return {"response": "not json" if len(calls) == 1 else '{"summary":"Ready","certainty":"known"}'}

    result = OllamaStructuredOutputAdapter("local-model", request_fn=fake).generate_and_validate("Summarize.", _structured_contract())
    assert result["status"] == "REPAIRED"
    assert "format" not in calls[0]
    assert "PREVIOUS_OUTPUT" in calls[1]["prompt"]


def test_native_json_mode_still_passes_through_the_same_lce_gateway():
    captured = {}

    def fake(_, payload, __):
        captured.update(payload)
        return {"response": '{"summary":"Ready","certainty":"uncertain"}'}

    result = OllamaStructuredOutputAdapter("local-model", profile=OllamaOutputProfile(native_json_mode=True), request_fn=fake).generate_and_validate("Summarize.", _structured_contract())
    assert result["accepted"]
    assert captured["format"] == "json"


def test_profile_passes_lce_context_and_rejects_known_without_evidence():
    captured = {}
    def fake(_, payload, __):
        captured.update(payload)
        return {"response": '{"summary":"Ready","certainty":"known"}'}
    profile=OllamaOutputProfile(require_evidence_for_known=True)
    result=OllamaStructuredOutputAdapter("local-model", profile=profile, request_fn=fake).generate_and_validate("Summarize.", _structured_contract(), context_summary="Budget must not increase.")
    assert result["status"] == "SEMANTIC_REJECTED"
    assert result["violations"] == ["CERTAINTY_REQUIRES_EVIDENCE"]
    assert "LCE_CONTEXT_SUMMARY=Budget must not increase." in captured["prompt"]


def test_adapter_preserves_context_and_evidence_for_repair():
    calls = []

    def fake(_, payload, __):
        calls.append(payload)
        return {"response": "not json" if len(calls) == 1 else '{"summary":"Ready","certainty":"uncertain"}'}

    result = OllamaStructuredOutputAdapter("local-model", request_fn=fake).generate_and_validate(
        "Summarize.",
        _structured_contract(),
        context_summary="Budget is fixed.",
        evidence_summary="evidence.budget.fixed supports the limit.",
    )
    assert result["status"] == "REPAIRED"
    assert "LCE_CONTEXT_SUMMARY=Budget is fixed." in calls[0]["prompt"]
    assert "LCE_EVIDENCE_SUMMARY=evidence.budget.fixed supports the limit." in calls[0]["prompt"]
    assert "LCE_CONTEXT_SUMMARY=Budget is fixed." in calls[1]["prompt"]
    assert "LCE_EVIDENCE_SUMMARY=evidence.budget.fixed supports the limit." in calls[1]["prompt"]


def test_adapter_rejects_known_value_when_evidence_claim_contradicts_it():
    contract = StructuredOutputContract(
        contract_id="assured-v1",
        schema={
            "type": "object",
            "properties": {
                "request_kind": {"type": "string", "enum": ["implementation_plan"]},
                "summary": {"type": "string"},
                "certainty": {"type": "string", "enum": ["known", "uncertain"]},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["request_kind", "summary", "certainty", "evidence_refs"],
            "additionalProperties": False,
        },
    )
    policy = StructuredAssurancePolicy.from_dict({
        "policy_id": "assured-v1",
        "required_values": {"request_kind": "implementation_plan"},
        "required_terms": {"summary": ["health"]},
        "certainty_path": "certainty",
        "evidence_refs_path": "evidence_refs",
        "required_evidence_claim_ids": ["evidence.health"],
    })
    adapter = OllamaStructuredOutputAdapter(
        "local-model",
        request_fn=lambda *_: {"response": '{"request_kind":"implementation_plan","summary":"Add health endpoint.","certainty":"known","evidence_refs":["evidence.health"]}'},
    )
    result = adapter.generate_and_validate(
        "Plan the health endpoint.",
        contract,
        assurance_policy=policy,
        evidence_claims={"evidence.health": EvidenceClaim("evidence.health", "contradicts")},
    )
    assert result["status"] == "SEMANTIC_REJECTED"
    assert result["violations"] == ["CERTAINTY_EVIDENCE_CONTRADICTED"]
    assert result["trace"]["structural_status"] == "ACCEPTED"


def test_adapter_declares_model_owned_content_safety_responsibility():
    result = OllamaStructuredOutputAdapter(
        "local-model",
        request_fn=lambda *_: {"response": '{"summary":"Ready","certainty":"uncertain"}'},
    ).generate_and_validate("Summarize.", _structured_contract())
    assert result["safety_responsibility"]["owner"] == "model"
    assert result["safety_responsibility"]["lce_content_refusal"] is False
