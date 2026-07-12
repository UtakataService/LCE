from lce_validation.runtime.controlled_generation import GenerationRequest, execute_controlled_generation
from lce_validation.runtime.conversation_contract import empty_conversation_state
from lce_validation.runtime.conversation_reducer import reduce_turn


class _Adapter:
    model_id = "fake-pilot"

    def __init__(self, candidate):
        self.candidate = candidate

    def generate(self, request):
        return self.candidate


def _request(text="Explain that briefly."):
    transition = reduce_turn(empty_conversation_state(session_id="generation-test"), text)
    return GenerationRequest(
        request_id="req-001",
        prompt="private prompt text",
        plan=transition["plan"],
        envelope=transition["flexible_response_envelope"],
        max_output_chars=120,
    )


def test_adapter_candidate_is_accepted_only_when_lce_envelope_allows_it():
    request = _request()
    result = execute_controlled_generation(_Adapter({"text": "Could you add one concrete detail?", "response_step": "clarify", "claim_uses": [], "markers": ["uncertainty_boundary"]}), request)

    assert result["accepted"]
    assert "private prompt text" not in str(result["trace"])


def test_adapter_candidate_with_unsupported_claim_is_rejected_and_redacted():
    request = _request()
    result = execute_controlled_generation(_Adapter({"text": "This is certainly true.", "response_step": "clarify", "claim_uses": ["fact_assertion"], "markers": ["uncertainty_boundary"]}), request)

    assert not result["accepted"]
    assert result["violations"] == ["PROHIBITED_CLAIM_USE"]
    assert "text" not in result["candidate"]


def test_adapter_candidate_missing_required_uncertainty_marker_is_rejected():
    request = _request()
    result = execute_controlled_generation(_Adapter({"text": "Could you add one concrete detail?", "response_step": "clarify", "claim_uses": [], "markers": []}), request)

    assert not result["accepted"]
    assert result["violations"] == ["REQUIRED_MARKER_MISSING"]
