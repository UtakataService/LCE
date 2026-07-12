"""Ollama adapter that emits candidates for the LCE controlled-generation gate."""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

from .controlled_generation import GenerationRequest
from .structured_output_gateway import (
    StructuredOutputContract,
    build_structured_output_instruction,
    process_structured_output,
)
from .structured_assurance import EvidenceClaim, StructuredAssurancePolicy, assess_structured_value
from .safety_responsibility import SafetyResponsibilityPolicy, resolve_safety_responsibility


class OllamaAdapterError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OllamaOutputProfile:
    native_json_mode: bool = False
    allow_fenced_json: bool = True
    max_repairs: int = 1
    require_evidence_for_known: bool = False


class OllamaControlledAdapter:
    """Local Ollama model adapter. Candidate acceptance remains outside this class."""

    def __init__(
        self,
        model_id: str,
        *,
        endpoint: str = "http://127.0.0.1:11434/api/generate",
        timeout_sec: int = 180,
        request_fn: Callable[[str, dict[str, Any], int], Mapping[str, Any]] | None = None,
    ) -> None:
        self.model_id = model_id
        self._endpoint = endpoint
        self._timeout_sec = timeout_sec
        self._request_fn = request_fn or _ollama_generate

    def generate(self, request: GenerationRequest) -> Mapping[str, Any]:
        payload = {
            "model": self.model_id,
            "prompt": _prompt(request),
            "format": "json",
            "stream": False,
            # Gemma thinking variants can otherwise return a thought object
            # instead of the requested response contract.
            "think": False,
            "options": {"temperature": 0},
        }
        response = self._request_fn(self._endpoint, payload, self._timeout_sec)
        raw = response.get("response")
        if not isinstance(raw, str):
            raise OllamaAdapterError("OLLAMA_RESPONSE_MISSING_TEXT")
        try:
            candidate = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaAdapterError("OLLAMA_RESPONSE_NOT_JSON") from exc
        if not isinstance(candidate, Mapping):
            raise OllamaAdapterError("OLLAMA_RESPONSE_NOT_OBJECT")
        return dict(candidate)


class OllamaStructuredOutputAdapter:
    """Use any local Ollama model through the LCE structured-output gateway.

    Native JSON mode is optional. Either path returns raw model text to LCE,
    which remains responsible for validation, safe defaults, and retries.
    """

    def __init__(
        self,
        model_id: str,
        *,
        endpoint: str = "http://127.0.0.1:11434/api/generate",
        timeout_sec: int = 180,
        profile: OllamaOutputProfile | None = None,
        request_fn: Callable[[str, dict[str, Any], int], Mapping[str, Any]] | None = None,
    ) -> None:
        self.model_id = model_id
        self._endpoint = endpoint
        self._timeout_sec = timeout_sec
        self._profile = profile or OllamaOutputProfile()
        self._request_fn = request_fn or _ollama_generate

    def generate_and_validate(
        self,
        user_request: str,
        contract: StructuredOutputContract,
        *,
        context_summary: str = "",
        evidence_summary: str = "",
        assurance_policy: StructuredAssurancePolicy | None = None,
        evidence_claims: Mapping[str, EvidenceClaim | Mapping[str, Any]] | None = None,
        safety_responsibility_policy: SafetyResponsibilityPolicy | None = None,
    ) -> dict[str, Any]:
        effective = replace(contract, allow_fenced_json=self._profile.allow_fenced_json, max_repairs=self._profile.max_repairs)
        raw = self._generate_raw(build_structured_output_instruction(
            user_request,
            effective,
            context_summary=context_summary,
            evidence_summary=evidence_summary,
        ))
        result = process_structured_output(
            raw,
            effective,
            repair_fn=self._generate_raw if effective.max_repairs else None,
            user_request=user_request,
            repair_context_summary=context_summary,
            repair_evidence_summary=evidence_summary,
        )
        if result["accepted"] and assurance_policy is not None:
            assurance = assess_structured_value(result["value"], assurance_policy, evidence_claims)
            result["assurance"] = assurance
            if not assurance["accepted"]:
                _semantic_reject(result, assurance["violations"])
        if result["accepted"] and assurance_policy is None and self._profile.require_evidence_for_known and result["value"].get("certainty") == "known" and not evidence_summary.strip():
            _semantic_reject(result, ["CERTAINTY_REQUIRES_EVIDENCE"])
        result["safety_responsibility"] = resolve_safety_responsibility(
            "content_generation",
            safety_responsibility_policy,
        )
        return result

    def _generate_raw(self, prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
        }
        if self._profile.native_json_mode:
            payload["format"] = "json"
        response = self._request_fn(self._endpoint, payload, self._timeout_sec)
        raw = response.get("response")
        if not isinstance(raw, str):
            raise OllamaAdapterError("OLLAMA_RESPONSE_MISSING_TEXT")
        return raw


def _prompt(request: GenerationRequest) -> str:
    envelope = request.envelope
    contract = {
        "response_step": list(envelope.get("allowed_response_steps", [])),
        "prohibited_claim_uses": list(envelope.get("prohibited_uses", [])),
        "required_markers": list(envelope.get("required_markers", [])),
        "max_output_chars": request.max_output_chars,
    }
    return (
        "Return only one JSON object with keys text, response_step, claim_uses, markers. "
        "Choose response_step only from the allowed list. Do not include prohibited claim uses. "
        "Include every required marker literally in markers. Do not add factual claims unless allowed.\n"
        f"CONTRACT={json.dumps(contract, ensure_ascii=False, sort_keys=True)}\n"
        f"USER_INPUT={request.prompt}"
    )


def _ollama_generate(endpoint: str, payload: dict[str, Any], timeout_sec: int) -> Mapping[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            loaded = json.load(response)
    except OSError as exc:
        raise OllamaAdapterError("OLLAMA_REQUEST_FAILED") from exc
    if not isinstance(loaded, Mapping):
        raise OllamaAdapterError("OLLAMA_RESPONSE_INVALID")
    return loaded


def _semantic_reject(result: dict[str, Any], violations: list[str]) -> None:
    result["trace"]["structural_status"] = result["status"]
    result["trace"]["status"] = "SEMANTIC_REJECTED"
    result.update({"status": "SEMANTIC_REJECTED", "accepted": False, "value": None, "violations": sorted(set(violations))})
