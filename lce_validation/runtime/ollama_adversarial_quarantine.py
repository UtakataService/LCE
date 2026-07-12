"""Gemma-generated adversarial input ideas, quarantined before fixture promotion."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen


class AdversarialCandidateError(ValueError):
    pass


ALLOWED_TAGS = {"privacy", "correction", "topic_shift", "unknown", "structured_output"}


def generate_adversarial_candidate(*, model_id: str, model_digest: str, target_tag: str, request_fn: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if target_tag not in ALLOWED_TAGS:
        raise AdversarialCandidateError("INVALID_ADVERSARIAL_TAG")
    payload = {
        "model": model_id, "format": "json", "stream": False, "think": False, "options": {"temperature": 0},
        "prompt": (
            "Return only JSON with keys input_text and phenomenon_tags. input_text must be a single harmless test input. "
            "phenomenon_tags must be a JSON array containing exactly one requested tag. Do not include real credentials, "
            "personal data, threats, or factual assertions. Requested tag=" + target_tag
        ),
    }
    raw = (request_fn or _request)(payload).get("response")
    if not isinstance(raw, str):
        raise AdversarialCandidateError("ADVERSARIAL_RESPONSE_MISSING")
    try:
        generated = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AdversarialCandidateError("ADVERSARIAL_RESPONSE_NOT_JSON") from exc
    if not isinstance(generated, Mapping) or not isinstance(generated.get("input_text"), str) or not generated["input_text"].strip():
        raise AdversarialCandidateError("INVALID_ADVERSARIAL_CANDIDATE")
    tags = generated.get("phenomenon_tags")
    if tags != [target_tag]:
        raise AdversarialCandidateError("INVALID_ADVERSARIAL_TAGS")
    return {
        "schema_version": "lce-adversarial-candidate/v1", "status": "QUARANTINED", "input_text": generated["input_text"],
        "phenomenon_tags": tags, "review_flags": ["MODEL_AUTHORED", "HUMAN_GOLD_REQUIRED", "DO_NOT_ADD_TO_BLIND_WITHOUT_SPLITTER"],
        "provenance": {"model_id": model_id, "model_digest": model_digest, "request_hash": _hash(payload)},
    }


def append_adversarial_quarantine(path: str | Path, candidate: Mapping[str, Any]) -> None:
    if candidate.get("status") != "QUARANTINED":
        raise AdversarialCandidateError("ADVERSARIAL_NOT_QUARANTINED")
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(candidate), ensure_ascii=False, sort_keys=True) + "\n")


def _request(payload: dict[str, Any]) -> Mapping[str, Any]:
    request = Request("http://127.0.0.1:11434/api/generate", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=180) as response: data = json.load(response)
    except OSError as exc:
        raise AdversarialCandidateError("ADVERSARIAL_REQUEST_FAILED") from exc
    return data if isinstance(data, Mapping) else {}


def _hash(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(dict(value), ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
