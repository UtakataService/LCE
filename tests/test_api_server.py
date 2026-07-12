import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lce_validation.api_server import create_server


def _request(server, path, payload=None):
    url = f"http://127.0.0.1:{server.server_port}{path}"
    if payload is None:
        with urlopen(url, timeout=5) as response:
            return response.status, json.load(response)
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=5) as response:
        return response.status, json.load(response)


def _with_server(callback):
    server = create_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        return callback(server)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _contract():
    return {
        "contract_id": "summary-v1",
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "certainty": {"type": "string", "enum": ["known", "uncertain"]},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "certainty", "evidence_refs"],
            "additionalProperties": False,
        },
    }


def test_health_and_capabilities_are_available():
    def check(server):
        status, health = _request(server, "/health")
        assert status == 200 and health["ok"]
        status, capabilities = _request(server, "/v1/capabilities")
        assert status == 200 and capabilities["model_execution"] == "caller_owned"
    _with_server(check)


def test_structured_gate_accepts_valid_uncertain_model_output():
    def check(server):
        status, result = _request(server, "/v1/gate/structured-output", {
            "raw_output": '{"summary":"Need more evidence.","certainty":"uncertain","evidence_refs":[]}',
            "contract": _contract(),
        })
        assert status == 200
        assert result["decision"] == "ACCEPT"
        assert result["result"]["value"]["certainty"] == "uncertain"
    _with_server(check)


def test_structured_gate_returns_model_repair_path_for_invalid_json():
    def check(server):
        status, result = _request(server, "/v1/gate/structured-output", {"raw_output": "not json", "contract": _contract()})
        assert status == 200
        assert result["decision"] == "RETURN_TO_MODEL"
        assert result["caller_next_step"] == "send_repair_instruction_to_generator"
    _with_server(check)


def test_structured_gate_holds_known_result_without_required_evidence():
    def check(server):
        status, result = _request(server, "/v1/gate/structured-output", {
            "raw_output": '{"summary":"Budget is fixed.","certainty":"known","evidence_refs":[]}',
            "contract": _contract(),
            "assurance_policy": {
                "policy_id": "evidence-v1",
                "certainty_path": "certainty",
                "evidence_refs_path": "evidence_refs",
                "required_evidence_claim_ids": ["budget.source"],
            },
            "evidence_claims": {},
        })
        assert status == 200
        assert result["decision"] == "HOLD"
        assert "CERTAINTY_EVIDENCE_REQUIRED_CLAIM_MISSING" in result["result"]["violations"]
    _with_server(check)


def test_candidate_gate_holds_state_commit_without_authorization():
    def check(server):
        status, result = _request(server, "/v1/gate/candidate", {
            "candidate": {
                "candidate_id": "candidate-1", "modality": "model", "claim_type": "tool_plan",
                "value": {"tool": "calendar.read"}, "confidence": 0.9,
                "evidence_refs": ["request-1"], "producer_id": "demo", "input_digest": "sha256:request",
                "action_scope": "state_commit",
            },
            "policy": {
                "policy_id": "candidate-v1", "allowed_modalities": ["model"], "allowed_claim_types": ["tool_plan"],
                "required_evidence_kinds": ["request_trace"], "allowed_action_scopes": ["display", "state_commit"],
            },
            "evidence_catalog": {"request-1": {"evidence_id": "request-1", "kind": "request_trace", "source_digest": "sha256:request"}},
        })
        assert status == 200
        assert result["decision"] == "HOLD"
        assert "AUTHORIZATION_REQUIRED" in result["result"]["reasons"]
    _with_server(check)


def test_unknown_endpoint_returns_json_error():
    def check(server):
        url = f"http://127.0.0.1:{server.server_port}/unknown"
        try:
            urlopen(url, timeout=5)
        except HTTPError as exc:
            assert exc.code == 404
            assert json.load(exc)["error"]["code"] == "ENDPOINT_NOT_FOUND"
        else:
            raise AssertionError("expected HTTP 404")
    _with_server(check)
