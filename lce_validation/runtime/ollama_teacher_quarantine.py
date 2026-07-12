"""Generate model-authored teaching candidates that remain quarantined by default."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen


class TeacherCandidateError(ValueError):
    pass


def generate_teacher_candidate(
    *,
    model_id: str,
    model_digest: str,
    seed_id: str,
    seed_text: str,
    language: str,
    request_fn: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if language not in {"en", "ja"}:
        raise TeacherCandidateError("UNSUPPORTED_TEACHER_LANGUAGE")
    request = {
        "model": model_id,
        "format": "json",
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
        "prompt": (
            "Return only JSON with keys input_variant, candidate_response, claim_uses, review_flags. "
            "input_variant and candidate_response must each be one plain JSON string, never an object or array. "
            "Create one safe paraphrase and a clarification-style response. Do not introduce facts, citations, "
            "personal data, or instructions for high-impact decisions. claim_uses must be an empty JSON array. "
            f"Language={language}. Seed={seed_text}"
        ),
    }
    raw_response = (request_fn or _ollama_request)(request).get("response")
    if not isinstance(raw_response, str):
        raise TeacherCandidateError("TEACHER_RESPONSE_MISSING")
    try:
        generated = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise TeacherCandidateError("TEACHER_RESPONSE_NOT_JSON") from exc
    if not isinstance(generated, Mapping):
        raise TeacherCandidateError("TEACHER_RESPONSE_NOT_OBJECT")
    _validate_generated(generated)
    record = {
        "schema_version": "lce-teacher-candidate/v1",
        "candidate_id": "teacher:" + _hash({"model": model_digest, "seed": seed_id, "generated": dict(generated)})[7:23],
        "status": "QUARANTINED",
        "source_seed_id": seed_id,
        "source_seed_hash": _hash({"seed_text": seed_text}),
        "language": language,
        "input_variant": generated["input_variant"],
        "candidate_response": generated["candidate_response"],
        "claim_uses": list(generated["claim_uses"]),
        "review_flags": sorted(set(generated["review_flags"] + ["MODEL_AUTHORED", "HUMAN_REVIEW_REQUIRED"])),
        "provenance": {"model_id": model_id, "model_digest": model_digest, "request_hash": _hash(request)},
    }
    return record


def append_quarantined_candidate(path: str | Path, record: Mapping[str, Any]) -> None:
    if record.get("status") != "QUARANTINED":
        raise TeacherCandidateError("TEACHER_CANDIDATE_NOT_QUARANTINED")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + "\n")


def _validate_generated(value: Mapping[str, Any]) -> None:
    required = {"input_variant", "candidate_response", "claim_uses", "review_flags"}
    if required - set(value) or not isinstance(value["input_variant"], str) or not isinstance(value["candidate_response"], str):
        raise TeacherCandidateError("INVALID_TEACHER_CANDIDATE")
    if not value["input_variant"].strip() or not value["candidate_response"].strip() or len(value["candidate_response"]) > 1200:
        raise TeacherCandidateError("INVALID_TEACHER_TEXT")
    if value["claim_uses"] != [] or not isinstance(value["review_flags"], list) or not all(isinstance(item, str) for item in value["review_flags"]):
        raise TeacherCandidateError("UNSAFE_TEACHER_CANDIDATE")


def _ollama_request(payload: dict[str, Any]) -> Mapping[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request("http://127.0.0.1:11434/api/generate", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=180) as response:
            data = json.load(response)
    except OSError as exc:
        raise TeacherCandidateError("TEACHER_REQUEST_FAILED") from exc
    if not isinstance(data, Mapping):
        raise TeacherCandidateError("TEACHER_RESPONSE_INVALID")
    return data


def _hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(value), ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
