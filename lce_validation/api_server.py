"""Portable stdlib HTTP API for bounded LCE control gates."""
from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping

from .runtime.acceptance_challenge import challenge_accepted_result
from .runtime.candidate_assurance import assess_candidate
from .runtime.structured_assurance import StructuredAssurancePolicy, assess_structured_value
from .runtime.structured_output_gateway import StructuredOutputContract, process_structured_output


API_VERSION = "v1"
MAX_REQUEST_BYTES = 1_000_000


class LceApiHandler(BaseHTTPRequestHandler):
    """JSON-only local API; model and tool execution remain outside this server."""

    server_version = "LCE-API/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(HTTPStatus.OK, {"ok": True, "service": "lce-api", "api_version": API_VERSION})
        elif self.path == "/v1/capabilities":
            self._send(HTTPStatus.OK, _capabilities())
        elif self.path == "/v1/openapi.json":
            self._send(HTTPStatus.OK, _openapi())
        else:
            self._error(HTTPStatus.NOT_FOUND, "ENDPOINT_NOT_FOUND")

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._json_body()
            if self.path == "/v1/gate/structured-output":
                result = _gate_structured_output(payload)
            elif self.path == "/v1/gate/candidate":
                result = _gate_candidate(payload)
            elif self.path == "/v1/gate/acceptance-challenge":
                result = _gate_acceptance_challenge(payload)
            else:
                self._error(HTTPStatus.NOT_FOUND, "ENDPOINT_NOT_FOUND")
                return
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except (KeyError, TypeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, f"INVALID_REQUEST:{type(exc).__name__}")
            return
        self._send(HTTPStatus.OK, result)

    def _json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("CONTENT_LENGTH_REQUIRED")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("INVALID_CONTENT_LENGTH") from exc
        if not 0 <= length <= MAX_REQUEST_BYTES:
            raise ValueError("PAYLOAD_TOO_LARGE")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("INVALID_JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("JSON_OBJECT_REQUIRED")
        return value

    def _send(self, status: HTTPStatus, value: Mapping[str, Any]) -> None:
        body = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, code: str) -> None:
        self._send(status, {"ok": False, "error": {"code": code}})

    def log_message(self, _format: str, *_args: Any) -> None:
        """Keep the library server quiet; deployers can wrap it with their logger."""


def create_server(host: str = "127.0.0.1", port: int = 8789) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), LceApiHandler)


def _gate_structured_output(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_output = payload.get("raw_output")
    if not isinstance(raw_output, str):
        raise ValueError("RAW_OUTPUT_REQUIRED")
    contract = _contract_from_dict(payload.get("contract"))
    result = process_structured_output(
        raw_output,
        contract,
        user_request=_bounded_text(payload.get("user_request", ""), "INVALID_USER_REQUEST"),
        repair_context_summary=_bounded_text(payload.get("context_summary", ""), "INVALID_CONTEXT_SUMMARY"),
        repair_evidence_summary=_bounded_text(payload.get("evidence_summary", ""), "INVALID_EVIDENCE_SUMMARY"),
    )
    raw_policy = payload.get("assurance_policy")
    if result["accepted"] and raw_policy is not None:
        policy = StructuredAssurancePolicy.from_dict(_object(raw_policy, "INVALID_ASSURANCE_POLICY"))
        assurance = assess_structured_value(result["value"], policy, _object(payload.get("evidence_claims", {}), "INVALID_EVIDENCE_CLAIMS"))
        result["assurance"] = assurance
        if not assurance["accepted"]:
            result["trace"]["structural_status"] = result["status"]
            result.update({"status": "SEMANTIC_REJECTED", "accepted": False, "value": None, "violations": assurance["violations"]})
    return {
        "ok": True,
        "api_version": API_VERSION,
        "gate": "structured_output",
        "decision": _structured_decision(result),
        "result": result,
        "caller_next_step": _structured_next_step(result),
        "claim_boundary": "The API validates declared structure and policy. It does not call an LLM, verify truth, or authorize external execution.",
    }


def _gate_candidate(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = assess_candidate(
        _object(payload.get("candidate"), "CANDIDATE_REQUIRED"),
        _object(payload.get("policy"), "POLICY_REQUIRED"),
        _object(payload.get("evidence_catalog", {}), "INVALID_EVIDENCE_CATALOG"),
    )
    return {
        "ok": True,
        "api_version": API_VERSION,
        "gate": "candidate",
        "decision": result["decision"],
        "result": result,
        "caller_next_step": "return_candidate" if result["accepted"] else "hold_or_revise_candidate",
    }


def _gate_acceptance_challenge(payload: Mapping[str, Any]) -> dict[str, Any]:
    signals = payload.get("signals", [])
    if not isinstance(signals, list):
        raise ValueError("INVALID_SIGNALS")
    result = challenge_accepted_result(
        _object(payload.get("result"), "RESULT_REQUIRED"),
        _object(payload.get("policy"), "POLICY_REQUIRED"),
        _object(payload.get("evidence_catalog", {}), "INVALID_EVIDENCE_CATALOG"),
        signals,
    )
    return {
        "ok": True,
        "api_version": API_VERSION,
        "gate": "acceptance_challenge",
        "decision": result["decision"],
        "result": result,
        "caller_next_step": "continue" if result["decision"] == "CLEAR" else "pause_and_review",
    }


def _contract_from_dict(value: Any) -> StructuredOutputContract:
    raw = _object(value, "CONTRACT_REQUIRED")
    return StructuredOutputContract(
        contract_id=raw.get("contract_id", ""),
        schema=raw.get("schema"),
        defaults=raw.get("defaults"),
        max_repairs=raw.get("max_repairs", 0),
        allow_fenced_json=raw.get("allow_fenced_json", True),
        max_output_chars=raw.get("max_output_chars", 12000),
    )


def _object(value: Any, error: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(error)
    return value


def _bounded_text(value: Any, error: str) -> str:
    if not isinstance(value, str) or len(value) > 4000:
        raise ValueError(error)
    return value


def _structured_decision(result: Mapping[str, Any]) -> str:
    if result.get("accepted"):
        return "ACCEPT"
    if result.get("status") == "RETRY_REQUIRED":
        return "RETURN_TO_MODEL"
    return "HOLD"


def _structured_next_step(result: Mapping[str, Any]) -> str:
    if result.get("accepted"):
        return "return_validated_value"
    if result.get("status") == "RETRY_REQUIRED":
        return "send_repair_instruction_to_generator"
    return "hold_for_evidence_or_policy_review"


def _capabilities() -> dict[str, Any]:
    return {
        "ok": True,
        "api_version": API_VERSION,
        "endpoints": {
            "/v1/gate/structured-output": "Validate a raw model/program JSON candidate against a contract and declared policy.",
            "/v1/gate/candidate": "Assess a typed model, program, or sensor candidate.",
            "/v1/gate/acceptance-challenge": "Pause an accepted result when declared challenge signals require review.",
        },
        "model_execution": "caller_owned",
        "tool_execution": "caller_owned",
        "state_commit": "caller_owned",
    }


def _openapi() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "LCE Control API", "version": API_VERSION, "description": "Bounded LCE validation API; model and tool execution remain caller-owned."},
        "paths": {
            "/health": {"get": {"summary": "Health check"}},
            "/v1/capabilities": {"get": {"summary": "Supported gates and ownership"}},
            "/v1/gate/structured-output": {"post": {"summary": "Gate raw JSON output from a model or program"}},
            "/v1/gate/candidate": {"post": {"summary": "Gate a typed candidate"}},
            "/v1/gate/acceptance-challenge": {"post": {"summary": "Challenge an accepted result"}},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local LCE Control API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8789)
    args = parser.parse_args()
    server = create_server(args.host, args.port)
    print(f"lce_api_listening: http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
