from lce_validation.runtime.capability_negotiation import assess_delegated_candidate, negotiate_capability


def _request(**extra):
    base={"required_capabilities":["web_research","long_context"],"lce_capabilities":["routing"],"lce_confidence":0.3,"local_confidence_threshold":0.8,"hard_gates":[]}
    base.update(extra); return base


def _models(): return [{"model_id":"frontier","enabled":True,"capabilities":["web_research","long_context"],"quality_score":9}]


def test_lce_defers_to_a_capable_model_instead_of_false_negative_deny():
    result=negotiate_capability(_request(),_models())
    assert result["decision"]=="DEFER_TO_MODEL" and result["model_id"]=="frontier"


def test_lce_exclusive_gate_cannot_be_overridden_by_model_capability():
    assert negotiate_capability(_request(hard_gates=["authorization_missing"]),_models())["decision"]=="DENY"


def test_lce_handles_a_sufficient_local_responsibility():
    result=negotiate_capability(_request(required_capabilities=["routing"],lce_confidence=.9),_models())
    assert result["decision"]=="HANDLE_LOCALLY"


def test_external_tuning_can_bias_a_borderline_request_toward_delegation():
    request=_request(required_capabilities=["routing"],lce_capabilities=["routing"],lce_confidence=.9)
    assert negotiate_capability(request,_models())["decision"]=="HANDLE_LOCALLY"
    assert negotiate_capability(request,_models(),parameters={"delegation_bias":1})["decision"]=="CLARIFY"


def test_external_tuning_can_require_a_higher_model_quality_floor():
    assert negotiate_capability(_request(),_models(),parameters={"model_quality_floor":10})["decision"]=="CLARIFY"


def test_delegated_candidate_is_rechecked_by_lce_after_model_call():
    negotiation=negotiate_capability(_request(),_models())
    assert assess_delegated_candidate(negotiation,{"structured_output_ok":True,"policy_ok":True,"state_ok":True})["accepted"]
    assert not assess_delegated_candidate(negotiation,{"structured_output_ok":True,"policy_ok":False,"state_ok":True})["accepted"]
