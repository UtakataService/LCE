"""Run a bounded same-candidate Gemma 4 E4B and LCE comparison.

This is a reference integration demonstration, not a quality benchmark. It
generates one candidate per case, then evaluates that exact raw candidate in
two modes: schema-only (`lm_only`) and schema plus declared assurance
(`lm_with_lce`).
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lce_validation.runtime.structured_assurance import StructuredAssurancePolicy, assess_structured_value
from lce_validation.runtime.structured_output_gateway import (
    StructuredOutputContract,
    build_structured_output_instruction,
    process_structured_output,
)


PROFILE_PATH = ROOT / "profiles" / "gemma4_e4b_reference_profile_v1.json"
CASES_PATH = Path(__file__).with_name("gemma4_e4b_reference_cases_v1.json")


def load_reference_inputs() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(profile, dict) or not isinstance(cases, list):
        raise ValueError("INVALID_REFERENCE_INPUTS")
    return profile, cases


def evaluate_same_candidate(raw_output: str, profile: Mapping[str, Any]) -> dict[str, Any]:
    contract = StructuredOutputContract(**profile["contract"])
    lm_only = process_structured_output(raw_output, contract, repair_fn=None)
    lm_with_lce = deepcopy(lm_only)
    if lm_with_lce["accepted"]:
        policy = StructuredAssurancePolicy.from_dict(profile["assurance_policy"])
        assurance = assess_structured_value(lm_with_lce["value"], policy, profile["evidence_claims"])
        lm_with_lce["assurance"] = assurance
        if not assurance["accepted"]:
            lm_with_lce["trace"]["structural_status"] = lm_with_lce["status"]
            lm_with_lce["trace"]["status"] = "SEMANTIC_REJECTED"
            lm_with_lce.update({
                "status": "SEMANTIC_REJECTED",
                "accepted": False,
                "value": None,
                "violations": assurance["violations"],
            })
    return {"lm_only": lm_only, "lm_with_lce": lm_with_lce}


def run_demo(
    *,
    model_id: str,
    endpoint: str,
    timeout_seconds: int,
    profile: Mapping[str, Any],
    cases: list[Mapping[str, Any]],
) -> dict[str, Any]:
    contract = StructuredOutputContract(**profile["contract"])
    rows: list[dict[str, Any]] = []
    for case in cases:
        prompt = build_structured_output_instruction(
            case["user_request"], contract, evidence_summary=case.get("evidence_summary", "")
        )
        started = time.perf_counter()
        response = _post_json(endpoint, {
            "model": model_id,
            "prompt": prompt,
            "format": "json" if profile["native_json_mode"] else None,
            "stream": False,
            "think": False,
            "options": profile["generation_options"],
        }, timeout_seconds)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        raw_output = response.get("response")
        if not isinstance(raw_output, str):
            raise RuntimeError("OLLAMA_RESPONSE_MISSING_TEXT")
        comparison = evaluate_same_candidate(raw_output, profile)
        rows.append({
            "case_id": case["case_id"],
            "language": case["language"],
            "generation_latency_ms": elapsed_ms,
            "raw_output_hash": _sha256(raw_output),
            **comparison,
        })
    metadata = _model_metadata(endpoint, model_id, timeout_seconds)
    return {
        "run_kind": "reference_integration_demo",
        "claim_boundary": profile["claim_boundary"],
        "profile_id": profile["profile_id"],
        "model": metadata,
        "case_count": len(rows),
        "rows": rows,
        "summary": {
            "lm_only_accepted": sum(row["lm_only"]["accepted"] for row in rows),
            "lm_with_lce_accepted": sum(row["lm_with_lce"]["accepted"] for row in rows),
            "lce_semantic_rejected": sum(row["lm_with_lce"]["status"] == "SEMANTIC_REJECTED" for row in rows),
        },
    }


def _model_metadata(endpoint: str, model_id: str, timeout_seconds: int) -> dict[str, Any]:
    parts = urlsplit(endpoint)
    tags_endpoint = urlunsplit((parts.scheme, parts.netloc, "/api/tags", "", ""))
    tags = _get_json(tags_endpoint, timeout_seconds).get("models", [])
    matched = next((row for row in tags if row.get("name") == model_id), {})
    details = matched.get("details", {}) if isinstance(matched, Mapping) else {}
    return {
        "id": model_id,
        "digest": matched.get("digest", "unavailable") if isinstance(matched, Mapping) else "unavailable",
        "parameter_size": details.get("parameter_size", "unavailable") if isinstance(details, Mapping) else "unavailable",
        "quantization_level": details.get("quantization_level", "unavailable") if isinstance(details, Mapping) else "unavailable",
    }


def _post_json(url: str, payload: Mapping[str, Any], timeout_seconds: int) -> dict[str, Any]:
    compact = {key: value for key, value in payload.items() if value is not None}
    request = Request(url, data=json.dumps(compact, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout_seconds) as response:
        loaded = json.load(response)
    if not isinstance(loaded, dict):
        raise RuntimeError("OLLAMA_RESPONSE_INVALID")
    return loaded


def _get_json(url: str, timeout_seconds: int) -> dict[str, Any]:
    with urlopen(url, timeout=timeout_seconds) as response:
        loaded = json.load(response)
    if not isinstance(loaded, dict):
        raise RuntimeError("OLLAMA_RESPONSE_INVALID")
    return loaded


def _sha256(value: str) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--out", required=True, help="Path for the generated JSON evidence.")
    args = parser.parse_args()
    profile, cases = load_reference_inputs()
    result = run_demo(
        model_id=args.model,
        endpoint=args.endpoint,
        timeout_seconds=args.timeout or profile["timeout_seconds"],
        profile=profile,
        cases=cases,
    )
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
