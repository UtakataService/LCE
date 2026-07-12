"""Model-agnostic controlled-generation boundary for future learned models.

The module does not implement language generation.  It makes every adapter
return a declared response step, claim uses, and markers so the LCE policy plan
can accept or reject an otherwise fluent candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Protocol


class ControlledGenerationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    request_id: str
    prompt: str
    plan: dict[str, Any]
    envelope: dict[str, Any]
    max_output_chars: int = 1200

    def trace_view(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "prompt_hash": _hash_text(self.prompt),
            "plan_id": self.plan.get("plan_id"),
            "allowed_steps": list(self.envelope.get("allowed_response_steps", [])),
            "prohibited_uses": list(self.envelope.get("prohibited_uses", [])),
        }


class LanguageModelAdapter(Protocol):
    model_id: str

    def generate(self, request: GenerationRequest) -> Mapping[str, Any]:
        """Return text plus explicit structural declarations; never persist prompt text."""


def execute_controlled_generation(adapter: LanguageModelAdapter, request: GenerationRequest) -> dict[str, Any]:
    _validate_request(request)
    candidate = dict(adapter.generate(request))
    errors = validate_generated_candidate(candidate, request)
    accepted = not errors
    return {
        "accepted": accepted,
        "model_id": str(adapter.model_id),
        "candidate": candidate if accepted else _redacted_candidate(candidate),
        "violations": errors,
        "trace": {
            **request.trace_view(),
            "model_id": str(adapter.model_id),
            "candidate_hash": _hash_json(candidate),
            "accepted": accepted,
        },
        "claim_boundary": "Adapter-contract result only; no model-quality or generalization claim follows from this acceptance.",
    }


def validate_generated_candidate(candidate: Mapping[str, Any], request: GenerationRequest) -> list[str]:
    required = {"text", "response_step", "claim_uses", "markers"}
    if not isinstance(candidate, Mapping) or required - set(candidate):
        return ["INVALID_GENERATION_CANDIDATE"]
    errors: list[str] = []
    text = candidate["text"]
    if not isinstance(text, str) or not text.strip():
        errors.append("EMPTY_GENERATION_TEXT")
    elif len(text) > request.max_output_chars:
        errors.append("MAX_OUTPUT_CHARS_EXCEEDED")
    allowed_steps = set(request.envelope.get("allowed_response_steps", []))
    if candidate["response_step"] not in allowed_steps:
        errors.append("RESPONSE_STEP_NOT_ALLOWED")
    claim_uses = candidate["claim_uses"]
    markers = candidate["markers"]
    if not isinstance(claim_uses, list) or not all(isinstance(item, str) for item in claim_uses):
        errors.append("INVALID_CLAIM_USES")
    elif set(claim_uses) & set(request.envelope.get("prohibited_uses", [])):
        errors.append("PROHIBITED_CLAIM_USE")
    if not isinstance(markers, list) or not all(isinstance(item, str) for item in markers):
        errors.append("INVALID_GENERATION_MARKERS")
    elif not set(request.envelope.get("required_markers", [])).issubset(markers):
        errors.append("REQUIRED_MARKER_MISSING")
    return sorted(set(errors))


def _validate_request(request: GenerationRequest) -> None:
    if not isinstance(request.request_id, str) or not request.request_id or not isinstance(request.prompt, str):
        raise ControlledGenerationError("INVALID_GENERATION_REQUEST")
    if not isinstance(request.plan, Mapping) or not isinstance(request.envelope, Mapping):
        raise ControlledGenerationError("INVALID_GENERATION_POLICY_CONTEXT")
    if not isinstance(request.max_output_chars, int) or not 1 <= request.max_output_chars <= 12000:
        raise ControlledGenerationError("INVALID_GENERATION_OUTPUT_BUDGET")


def _redacted_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {"candidate_hash": _hash_json(candidate), "response_step": candidate.get("response_step"), "rejected": True}


def _hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_json(value: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
