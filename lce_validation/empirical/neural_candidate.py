from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .nl_normalization import normalize_tokens
from .semantic_chunk import parse_semantic_chunks
from .seeded_dialogue import stable_seed


GENERATOR_VERSION = "small_neural_candidate_v3"
DEFAULT_MODEL = "bge-m3:latest"
DEFAULT_ENDPOINT = "http://127.0.0.1:11434/api/embed"
MAX_INPUT_CHARS = 4096
MAX_CANDIDATES = 3

CANDIDATE_PROTOTYPES = {
    "explain_state": "explain describe how something works give an explanation of current state",
    "continue_plan": "continue proceed with the previous plan task or design",
    "implement_task": "implement build create code parser function or system component",
    "verify_result": "verify validate test prove check correctness evidence or output",
    "compare_options": "compare alternatives options differences versus tradeoffs",
    "modify_system": "change modify update improve refactor an existing system",
    "request_evidence": "request evidence source citation provenance support for a claim",
    "clarify_reference": "clarify ambiguous missing target reference this that it or unclear request",
    "enforce_policy": "enforce policy safety approval confirmation prohibition deny dangerous action",
}

INTENT_LABEL = {
    "request_explanation": "explain_state",
    "continue_task": "continue_plan",
    "request_implementation": "implement_task",
    "request_verification": "verify_result",
    "request_comparison": "compare_options",
    "request_modification": "modify_system",
}


def generate_neural_candidates(
    text: str,
    *,
    backend: str = "heuristic",
    model_id: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    top_n: int = MAX_CANDIDATES,
    timeout_seconds: float = 30.0,
    fallback: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    bounded_text = text[:MAX_INPUT_CHARS]
    semantic = parse_semantic_chunks(bounded_text)
    backend_used = backend
    backend_error = ""
    actual_model_calls = 0
    try:
        if backend == "ollama_embedding":
            scores = _ollama_scores(bounded_text, model_id, endpoint, timeout_seconds)
            actual_model_calls = 1
        elif backend == "heuristic":
            scores = _heuristic_scores(bounded_text, semantic)
        else:
            raise ValueError("backend must be heuristic or ollama_embedding")
    except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
        if not fallback:
            raise
        backend_error = f"{type(exc).__name__}: {exc}"
        backend_used = "heuristic_fallback"
        scores = _heuristic_scores(bounded_text, semantic)

    policy = _policy_guard(bounded_text)
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:max(1, min(MAX_CANDIDATES, top_n))]
    candidates = [
        {
            "candidate_id": f"cand-{index:02d}-{label}",
            "label": label,
            "score": round(float(score), 6),
            "rank": index,
            "seed": stable_seed(f"{bounded_text}:{label}", salt="lce-neural-candidate-v3"),
            "backend": backend_used,
            "model_id": model_id if backend_used == "ollama_embedding" else "none",
            "provenance": "ollama_embedding_cosine" if backend_used == "ollama_embedding" else "semantic_slot_plus_lexical_overlap",
        }
        for index, (label, score) in enumerate(ranked, start=1)
    ]
    raw_candidate_labels = [row["label"] for row in candidates]
    control_injections: list[str] = []
    if policy["decision"] == "DENY" and "enforce_policy" not in raw_candidate_labels:
        candidates[-1] = {
            "candidate_id": "cand-control-enforce_policy",
            "label": "enforce_policy", "score": 1.0, "rank": 0,
            "seed": stable_seed(f"{bounded_text}:enforce_policy", salt="lce-neural-candidate-v3"),
            "backend": "deterministic_control", "model_id": "none",
            "provenance": "policy_guard_required_candidate",
        }
        candidates = sorted(candidates, key=lambda row: (-row["score"], row["label"]))
        for index, row in enumerate(candidates, start=1):
            row["rank"] = index
        control_injections.append("enforce_policy")
    validation = _validate_candidates(candidates)
    ambiguity = _ambiguity(candidates, semantic)
    authority = "REJECT_POLICY" if policy["decision"] == "DENY" else "ABSTAIN" if ambiguity["abstain"] else "PROPOSE_ONLY"
    response = f"Generated {len(candidates)} bounded candidates; authority={authority}; backend={backend_used}."
    return {
        "ok": validation["ok"],
        "generator_version": GENERATOR_VERSION,
        "input": text,
        "semantic_chunks": semantic["chunks"],
        "requested_backend": backend,
        "backend_used": backend_used,
        "backend_error": backend_error,
        "model_id": model_id,
        "actual_model_calls": actual_model_calls,
        "candidates": candidates,
        "raw_candidate_labels": raw_candidate_labels,
        "control_injections": control_injections,
        "validation": validation,
        "ambiguity": ambiguity,
        "policy_guard": policy,
        "authority_decision": authority,
        "response": response,
        "output_chunks": [
            {"chunk_id": f"out-{row['rank']:02d}", "role": "candidate", "seed": row["seed"], "text": f"{row['label']} score={row['score']:.6f} provenance={row['provenance']}"}
            for row in candidates
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "limits": {"max_input_chars": MAX_INPUT_CHARS, "max_candidates": MAX_CANDIDATES, "timeout_seconds": timeout_seconds},
        "claim": "bounded_local_candidate_proposal_only",
        "blocked_claims": [
            "candidate_is_verified_answer", "model_controls_policy", "general_language_understanding",
            "generative_llm_equivalence", "llm_quality_parity", "transformer_replacement",
        ],
    }


def run_neural_candidate_benchmark(
    cases_path: str | Path,
    out_dir: str | Path,
    *,
    backend: str = "heuristic",
    model_id: str = DEFAULT_MODEL,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in load_jsonl(cases_path):
        result = generate_neural_candidates(case["input"], backend=backend, model_id=model_id, timeout_seconds=timeout_seconds)
        labels = [row["label"] for row in result["candidates"]]
        raw_labels = result["raw_candidate_labels"]
        checks = {
            "expected_in_top_n": case["expected_label"] in labels,
            "expected_in_raw_top_n": case["expected_label"] in raw_labels,
            "policy": result["authority_decision"] == case.get("expected_authority", result["authority_decision"]),
            "schema": result["validation"]["ok"],
            "bounded": len(result["candidates"]) <= MAX_CANDIDATES,
        }
        final_checks = ("expected_in_top_n", "policy", "schema", "bounded")
        rows.append({"case_id": case["case_id"], "phenomenon_tags": case.get("phenomenon_tags", []), "checks": checks, "case_ok": all(checks[key] for key in final_checks), "result": result})
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name, "backend": backend, "model_id": model_id,
        "case_count": len(rows), "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "top_n_recall": _ratio(row["checks"]["expected_in_top_n"] for row in rows),
        "raw_top_n_recall": _ratio(row["checks"]["expected_in_raw_top_n"] for row in rows),
        "schema_accuracy": _ratio(row["checks"]["schema"] for row in rows),
        "actual_model_calls": sum(row["result"]["actual_model_calls"] for row in rows),
        "fallback_count": sum(1 for row in rows if row["result"]["backend_used"] == "heuristic_fallback"),
        "control_injection_count": sum(len(row["result"]["control_injections"]) for row in rows),
        "mean_elapsed_ms": round(sum(row["result"]["elapsed_ms"] for row in rows) / len(rows), 3) if rows else 0.0,
        "by_tag": _by_tag(rows),
        "claim": "bounded_local_candidate_proposal_only",
        "blocked_claims": ["model_quality_parity", "verified_answer_generation", "transformer_replacement"],
    }
    _write_jsonl(out / "neural_candidate_rows.jsonl", rows)
    (out / "neural_candidate_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _heuristic_scores(text: str, semantic: dict[str, Any]) -> dict[str, float]:
    query = set(normalize_tokens(text))
    scores = {}
    primary = semantic["chunks"][0] if semantic["chunks"] else {}
    preferred = INTENT_LABEL.get(primary.get("intent", ""))
    for label, prototype in CANDIDATE_PROTOTYPES.items():
        proto = set(normalize_tokens(prototype))
        overlap = len(query & proto) / len(query | proto) if query | proto else 0.0
        scores[label] = 0.62 + 0.3 * overlap if label == preferred else 0.05 + 0.45 * overlap
    if primary.get("references") or primary.get("ambiguity_flags"):
        scores["clarify_reference"] = max(scores["clarify_reference"], 0.7)
    if any(token in text.lower() for token in ("evidence", "source", "provenance")):
        scores["request_evidence"] = max(scores["request_evidence"], 0.72)
    if _policy_guard(text)["decision"] == "DENY":
        scores["enforce_policy"] = 1.0
    return scores


def _ollama_scores(text: str, model_id: str, endpoint: str, timeout: float) -> dict[str, float]:
    labels = sorted(CANDIDATE_PROTOTYPES)
    inputs = [text] + [CANDIDATE_PROTOTYPES[label] for label in labels]
    payload = json.dumps({"model": model_id, "input": inputs, "truncate": True}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    embeddings = data.get("embeddings", [])
    if len(embeddings) != len(inputs):
        raise ValueError("embedding response count mismatch")
    query = embeddings[0]
    return {label: max(0.0, min(1.0, (_cosine(query, embeddings[index]) + 1.0) / 2.0)) for index, label in enumerate(labels, start=1)}


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("invalid embedding dimensions")
    dot = sum(a * b for a, b in zip(left, right))
    a_norm = math.sqrt(sum(a * a for a in left))
    b_norm = math.sqrt(sum(b * b for b in right))
    return dot / (a_norm * b_norm) if a_norm and b_norm else 0.0


def _validate_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    errors = []
    labels = [row.get("label") for row in candidates]
    if len(candidates) > MAX_CANDIDATES:
        errors.append("candidate_limit_exceeded")
    if len(labels) != len(set(labels)):
        errors.append("duplicate_label")
    for row in candidates:
        if row.get("label") not in CANDIDATE_PROTOTYPES:
            errors.append("unknown_label")
        score = row.get("score")
        if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0.0 <= score <= 1.0:
            errors.append("invalid_score")
    return {"ok": not errors, "errors": sorted(set(errors)), "candidate_count": len(candidates)}


def _ambiguity(candidates: list[dict[str, Any]], semantic: dict[str, Any]) -> dict[str, Any]:
    margin = candidates[0]["score"] - candidates[1]["score"] if len(candidates) > 1 else 1.0
    flags = semantic["chunks"][0].get("ambiguity_flags", []) if semantic["chunks"] else ["empty_input"]
    abstain = bool(flags) and margin < 0.08
    return {"abstain": abstain, "top_margin": round(margin, 6), "semantic_flags": flags}


def _policy_guard(text: str) -> dict[str, str]:
    lowered = text.lower()
    approval = "approval" in lowered and "without approval" not in lowered and "no approval" not in lowered
    confirmation = "confirm" in lowered and "without confirmation" not in lowered
    if "delete" in lowered and not approval:
        return {"decision": "DENY", "reason": "delete requires approval"}
    if any(word in lowered for word in ("send", "publish", "external")) and not approval and not confirmation:
        return {"decision": "DENY", "reason": "external action requires approval or confirmation"}
    return {"decision": "ALLOW", "reason": "no blocking action pattern"}


def _ratio(values: Any) -> float:
    rows = list(values)
    return round(sum(1 for value in rows if value) / len(rows), 6) if rows else 0.0


def _by_tag(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        for tag in row["phenomenon_tags"]:
            item = result.setdefault(tag, {"case_count": 0, "case_ok": 0})
            item["case_count"] += 1
            item["case_ok"] += int(row["case_ok"])
    for item in result.values():
        item["accuracy"] = round(item["case_ok"] / item["case_count"], 6)
    return result


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
