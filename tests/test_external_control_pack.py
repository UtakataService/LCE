from lce_validation.runtime.external_control_pack import build_router_instruction, execute_external_plan, plan_external_request, validate_router_candidate
from lce_validation.runtime.model_pack import content_hash


def _pack():
    payload={"default_intent_id":"chat","retrieval_threshold":0.6,"intents":[
        {"intent_id":"chat","priority":1,"signals":{"any_terms":[]},"retrieval_policy":"never","context_strategy":"recent","model_classes":["fast"],"request_kind":"question"},
        {"intent_id":"research","priority":5,"signals":{"any_terms":["research","調査"]},"retrieval_policy":"when_unknown","context_strategy":"important","model_classes":["reasoner","fast"],"request_kind":"research"}],
        "models":[{"model_id":"fast-local","classes":["fast"],"enabled":True},{"model_id":"reasoner-local","classes":["reasoner"],"enabled":True}],
        "actions":[{"action_id":"web_search","status":"WEB_SEARCH","operation":"adapter","allowed_intent_ids":["research"],"decision_rule":{"mode":"when_signaled","any_terms":["latest","最新"],"criteria":"fresh information is requested"}},{"action_id":"verification_needed","status":"NEEDS_VERIFICATION","operation":"status","allowed_intent_ids":["research"],"decision_rule":{"mode":"when_unknown","criteria":"knowledge confidence is below threshold"}}]}
    return {"schema_version":"lce-pack/v1","pack_id":"control.reference","pack_version":"1","pack_type":"ControlPack","engine_compatibility":"lce-core/v1","content_hash":content_hash(payload),"capabilities":["control.routing.v1"],"payload":payload}


def test_pack_controls_research_retrieval_context_and_model_without_app_cases():
    plan=plan_external_request({"text":"この件を調査して","knowledge_confidence":0.2,"history":[{"id":"a","importance":1},{"id":"b","importance":9}]},_pack())
    assert plan["status"]=="READY" and plan["intent_id"]=="research"
    assert plan["retrieval"]["action"]=="RETRIEVE" and plan["model"]["model_id"]=="reasoner-local"
    assert plan["context"][0]["id"]=="b"


def test_known_research_can_skip_rag_and_router_prompt_is_constrained():
    plan=plan_external_request({"text":"research this","knowledge_confidence":0.9},_pack())
    assert plan["retrieval"]["action"]=="SKIP"
    assert "reasoner-local" in build_router_instruction({"text":"x"},_pack())


def test_execution_uses_only_selected_plan_and_declared_adapters():
    plan=plan_external_request({"text":"research this","knowledge_confidence":0.1},_pack())
    result=execute_external_plan(plan,{"text":"research this"},retrieve=lambda _: [{"id":"r1"}],model_invoke=lambda model,text,context,docs: {"model":model,"docs":len(docs)})
    assert result=={"status":"EXECUTED","model_id":"reasoner-local","response":{"model":"reasoner-local","docs":2},"retrieval_count":1,"action_count":1}


def test_router_llm_candidate_cannot_escape_pack_model_or_retrieval_rules():
    assert validate_router_candidate({"intent_id":"research","model_id":"reasoner-local","retrieval_action":"RETRIEVE"},_pack())["accepted"]
    assert not validate_router_candidate({"intent_id":"chat","model_id":"reasoner-local","retrieval_action":"RETRIEVE"},_pack())["accepted"]


def test_action_rules_call_only_appropriate_external_capabilities_or_return_status():
    plan=plan_external_request({"text":"最新の件を調査して","knowledge_confidence":0.1},_pack())
    assert [row["action_id"] for row in plan["actions"]]==["web_search","verification_needed"]
    result=execute_external_plan(plan,{"text":"最新の件を調査して"},retrieve=lambda _: [],action_adapters={"web_search": lambda _: {"hits": 2}},model_invoke=lambda *args: args[3])
    assert result["action_count"]==2 and result["response"][0]["action_id"]=="web_search"
