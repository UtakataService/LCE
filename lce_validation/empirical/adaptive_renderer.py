from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .graph_reasoning import run_graph_reasoning
from .seeded_dialogue import stable_seed


RENDERER_VERSION = "adaptive_verified_renderer_v5"
PROFILE_VERSION = "benchmark_profile_v1"
MAX_OUTPUT_CHARS = 1200
MAX_REPAIRS = 2
MAX_SECTIONS = 6
PROFILE_KEYS = {"profile_id", "style", "max_chars", "required_sections", "require_support_refs", "include_next_step", "forbidden_phrases"}
PROTECTED_FIDELITY_TERMS = {"blocked", "cannot", "deny", "evidence", "source", "conflict", "resolution", "clarification", "target", "accept", "selected", "support", "next step"}

BUILTIN_PROFILES = {
    "default": {"style": "balanced", "max_chars": 420, "required_sections": [], "require_support_refs": True, "include_next_step": True, "forbidden_phrases": []},
    "concise_qa": {"style": "concise", "max_chars": 180, "required_sections": ["Answer"], "require_support_refs": False, "include_next_step": False, "forbidden_phrases": []},
    "evidence_first": {"style": "evidence_first", "max_chars": 520, "required_sections": ["Evidence", "Answer"], "require_support_refs": True, "include_next_step": True, "forbidden_phrases": []},
    "instruction_following": {"style": "direct", "max_chars": 360, "required_sections": ["Result"], "require_support_refs": True, "include_next_step": True, "forbidden_phrases": []},
    "repair_explicit": {"style": "repair", "max_chars": 420, "required_sections": ["Status", "Required next step"], "require_support_refs": True, "include_next_step": True, "forbidden_phrases": []},
    "coding": {"style": "coding", "max_chars": 520, "required_sections": ["Plan", "Verification"], "require_support_refs": True, "include_next_step": True, "forbidden_phrases": []},
}

OUTCOME_TEXT = {
    "accepted_candidate": "The verified path accepts the bounded candidate '{candidate}' for further composition.",
    "blocked_policy": "The request is blocked by policy and cannot proceed through the candidate path.",
    "repair_evidence": "The request needs source evidence before a normal answer can be accepted.",
    "repair_conflict": "The request conflicts with accepted history and needs explicit resolution.",
    "repair_clarify": "The request has an unresolved reference and needs clarification before selection.",
}

NEXT_STEP = {
    "accepted_candidate": "Continue only with the selected supported path.",
    "blocked_policy": "Provide valid approval or choose a non-blocked action.",
    "repair_evidence": "Attach or identify a source that supports the requested claim.",
    "repair_conflict": "Choose which conflicting constraint should remain authoritative.",
    "repair_clarify": "Identify the exact target of the request.",
}


def render_verified_response(
    current_input: str,
    history: list[dict[str, str]] | None = None,
    *,
    profile: str | dict[str, Any] = "default",
) -> dict[str, Any]:
    reasoning = run_graph_reasoning(current_input, history or [])
    resolved = resolve_profile(profile)
    support_ids = _support_ids(reasoning)
    draft = _render(reasoning, resolved, support_ids)
    baseline_evaluation = evaluate_rendered_response(reasoning["response"], reasoning, resolved, support_ids)
    repair_trace = []
    response = draft
    evaluation = evaluate_rendered_response(response, reasoning, resolved, support_ids)
    for attempt in range(1, MAX_REPAIRS + 1):
        if evaluation["ok"]:
            break
        before = list(evaluation["errors"])
        response = _repair_response(response, reasoning, resolved, support_ids, before)
        evaluation = evaluate_rendered_response(response, reasoning, resolved, support_ids)
        repair_trace.append({"attempt": attempt, "errors_before": before, "errors_after": list(evaluation["errors"]), "response_chars": len(response)})
    chunks = _response_chunks(response, resolved)
    return {
        "ok": reasoning["ok"] and evaluation["ok"],
        "renderer_version": RENDERER_VERSION,
        "profile": resolved,
        "route": reasoning["route"],
        "outcome": reasoning["outcome"],
        "response": response,
        "output_chunks": chunks,
        "evaluation": evaluation,
        "baseline_evaluation": baseline_evaluation,
        "repair_trace": repair_trace,
        "repair_count": len(repair_trace),
        "support_ids": support_ids,
        "reasoning": reasoning,
        "uplift": round(evaluation["score"] - baseline_evaluation["score"], 6),
        "claim": "benchmark_adaptive_verified_rendering_only",
        "blocked_claims": [
            "renderer_adds_facts", "renderer_changes_policy", "benchmark_generalization_proven",
            "general_language_generation", "llm_quality_parity", "transformer_replacement",
        ],
    }


def resolve_profile(profile: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(profile, str):
        if profile not in BUILTIN_PROFILES:
            raise ValueError(f"unknown profile: {profile}")
        data = {"profile_id": profile, **BUILTIN_PROFILES[profile]}
    elif isinstance(profile, dict):
        base_id = str(profile.get("base", "default"))
        if base_id not in BUILTIN_PROFILES:
            raise ValueError(f"unknown base profile: {base_id}")
        data = {"profile_id": str(profile.get("profile_id", "custom")), **BUILTIN_PROFILES[base_id], **{key: value for key, value in profile.items() if key != "base"}}
    else:
        raise ValueError("profile must be a name or object")
    errors = _profile_errors(data)
    if errors:
        raise ValueError("invalid profile: " + ", ".join(errors))
    data["profile_version"] = PROFILE_VERSION
    data["max_chars"] = min(MAX_OUTPUT_CHARS, int(data["max_chars"]))
    return data


def evaluate_rendered_response(response: str, reasoning: dict[str, Any], profile: dict[str, Any], support_ids: list[str]) -> dict[str, Any]:
    errors = []
    lowered = response.lower()
    for section in profile["required_sections"]:
        if f"{section}:" not in response:
            errors.append(f"missing_section:{section}")
    if len(response) > profile["max_chars"]:
        errors.append("max_chars_exceeded")
    if profile["require_support_refs"] and support_ids and "[support:" not in response:
        errors.append("missing_support_ref")
    if profile["include_next_step"] and "next step" not in lowered and "required next step:" not in lowered:
        errors.append("missing_next_step")
    for phrase in profile["forbidden_phrases"]:
        if phrase.lower() in lowered:
            errors.append(f"forbidden_phrase:{phrase}")
    errors.extend(_fidelity_errors(lowered, reasoning["outcome"]))
    if any(claim.replace("_", " ") in lowered for claim in reasoning["blocked_claims"]):
        errors.append("blocked_claim_leak")
    dimensions = {
        "format_compliance": not any(error.startswith("missing_section") or error == "max_chars_exceeded" for error in errors),
        "grounding": "missing_support_ref" not in errors and "blocked_claim_leak" not in errors,
        "route_fidelity": not any(error.startswith("outcome_") for error in errors),
        "policy_fidelity": "outcome_policy_missing" not in errors,
        "profile_compliance": not any(error.startswith("forbidden_phrase") or error == "missing_next_step" for error in errors),
    }
    score = sum(int(value) for value in dimensions.values()) / len(dimensions)
    return {"ok": not errors, "errors": sorted(set(errors)), "dimensions": dimensions, "score": round(score, 6), "response_chars": len(response)}


def run_renderer_benchmark(cases_path: str | Path, out_dir: str | Path, *, split: str = "dev") -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in load_jsonl(cases_path):
        profile = case.get("profile", "default")
        result = render_verified_response(case["current_input"], case.get("history", []), profile=profile)
        checks = {
            "outcome": result["outcome"] == case["expected_outcome"],
            "render": result["evaluation"]["ok"],
            "contains": all(item.lower() in result["response"].lower() for item in case.get("required_contains", [])),
            "not_contains": all(item.lower() not in result["response"].lower() for item in case.get("forbidden_contains", [])),
            "bounded_repair": result["repair_count"] <= MAX_REPAIRS,
        }
        rows.append({"case_id": case["case_id"], "split": split, "phenomenon_tags": case.get("phenomenon_tags", []), "checks": checks, "case_ok": all(checks.values()), "result": result})
    summary = {
        "ok": all(row["case_ok"] for row in rows), "run_id": out.name, "split": split,
        "case_count": len(rows), "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "render_accuracy": _ratio(row["checks"]["render"] for row in rows),
        "outcome_accuracy": _ratio(row["checks"]["outcome"] for row in rows),
        "mean_score": _mean(row["result"]["evaluation"]["score"] for row in rows),
        "baseline_mean_score": _mean(row["result"]["baseline_evaluation"]["score"] for row in rows),
        "mean_uplift": _mean(row["result"]["uplift"] for row in rows),
        "repair_success_rate": _ratio(row["result"]["evaluation"]["ok"] for row in rows if row["result"]["repair_count"] > 0),
        "by_tag": _by_tag(rows),
        "claim": "benchmark_adaptive_verified_rendering_only",
        "blocked_claims": ["benchmark_generalization_proven", "llm_quality_parity", "transformer_replacement"],
    }
    _write_jsonl(out / f"renderer_{split}_rows.jsonl", rows)
    (out / f"renderer_{split}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def run_profile_validation_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in load_jsonl(cases_path):
        accepted = True
        error = ""
        try:
            resolved = resolve_profile(case["profile"])
        except ValueError as exc:
            accepted = False
            error = str(exc)
            resolved = None
        expected = bool(case["expected_valid"])
        rows.append({
            "case_id": case["case_id"], "phenomenon_tags": case.get("phenomenon_tags", []),
            "expected_valid": expected, "accepted": accepted, "case_ok": accepted == expected,
            "error": error, "resolved": resolved,
        })
    summary = {
        "ok": all(row["case_ok"] for row in rows), "run_id": out.name,
        "case_count": len(rows), "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "valid_acceptance_accuracy": _ratio(row["case_ok"] for row in rows if row["expected_valid"]),
        "invalid_rejection_accuracy": _ratio(row["case_ok"] for row in rows if not row["expected_valid"]),
        "by_tag": _by_tag(rows), "claim": "benchmark_profile_validation_only",
    }
    _write_jsonl(out / "profile_validation_rows.jsonl", rows)
    (out / "profile_validation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _render(reasoning: dict[str, Any], profile: dict[str, Any], support_ids: list[str]) -> str:
    outcome = reasoning["outcome"]
    candidate = reasoning["neural_candidates"]["candidates"][0]["label"]
    answer = OUTCOME_TEXT[outcome].format(candidate=candidate)
    support = _support_text(support_ids)
    next_step = NEXT_STEP[outcome]
    style = profile["style"]
    if style == "concise":
        parts = [f"Answer: {answer}"]
    elif style == "evidence_first":
        parts = [f"Evidence: {support}", f"Answer: {answer}"]
    elif style == "direct":
        parts = [f"Result: {answer}"]
    elif style == "repair":
        parts = [f"Status: {answer}", f"Required next step: {next_step}"]
    elif style == "coding":
        parts = [f"Plan: {answer}", f"Verification: {support}"]
    else:
        parts = [answer]
    if profile["require_support_refs"] and "[support:" not in " ".join(parts):
        parts.append(support)
    if profile["include_next_step"] and not any("next step" in part.lower() for part in parts):
        parts.append(f"Next step: {next_step}")
    return "\n".join(parts)


def _repair_response(response: str, reasoning: dict[str, Any], profile: dict[str, Any], support_ids: list[str], errors: list[str]) -> str:
    repaired = response
    for error in errors:
        if error.startswith("missing_section:"):
            section = error.split(":", 1)[1]
            repaired += f"\n{section}: {_section_content(section, reasoning, support_ids)}"
        elif error == "missing_support_ref":
            repaired += "\n" + _support_text(support_ids)
        elif error == "missing_next_step":
            repaired += f"\nNext step: {NEXT_STEP[reasoning['outcome']]}"
        elif error.startswith("forbidden_phrase:"):
            phrase = error.split(":", 1)[1]
            repaired = repaired.replace(phrase, "[removed]").replace(phrase.lower(), "[removed]")
    if len(repaired) > profile["max_chars"]:
        repaired = _compact_response(reasoning, profile, support_ids)
    return repaired


def _compact_response(reasoning: dict[str, Any], profile: dict[str, Any], support_ids: list[str]) -> str:
    outcome = reasoning["outcome"]
    compact = {
        "accepted_candidate": "Candidate accepted.",
        "blocked_policy": "Blocked by policy.",
        "repair_evidence": "Source evidence required.",
        "repair_conflict": "Conflict resolution required.",
        "repair_clarify": "Target clarification required.",
    }[outcome]
    parts = [f"{section}: {_compact_section_content(section, compact, outcome, support_ids)}" for section in profile["required_sections"]]
    if not parts:
        parts = [compact]
    if profile["require_support_refs"] and "[support:" not in " ".join(parts):
        parts.append(_compact_support_text(support_ids))
    if profile["include_next_step"] and not any("next step" in part.lower() for part in parts):
        parts.append(f"Next step: {_compact_next_step(outcome)}")
    text = "\n".join(parts)
    return text if len(text) <= profile["max_chars"] else text[:profile["max_chars"]].rstrip(" ,;:")


def _section_content(section: str, reasoning: dict[str, Any], support_ids: list[str]) -> str:
    candidate = reasoning["neural_candidates"]["candidates"][0]["label"]
    if section.lower() in {"evidence", "verification", "sources", "checks", "trace"}:
        return _support_text(support_ids)
    if "next step" in section.lower():
        return NEXT_STEP[reasoning["outcome"]]
    return OUTCOME_TEXT[reasoning["outcome"]].format(candidate=candidate)


def _support_ids(reasoning: dict[str, Any]) -> list[str]:
    return sorted({line["line_id"] for line in reasoning["lines"] if line["line_type"] in {"supports_output", "requires_evidence", "repairs", "policy_blocks", "tests"}})


def _support_text(support_ids: list[str]) -> str:
    refs = ",".join(support_ids[:2]) if support_ids else "none"
    return f"[support:{refs}]"


def _compact_support_text(support_ids: list[str]) -> str:
    return f"[support:{support_ids[0] if support_ids else 'none'}]"


def _compact_section_content(section: str, compact: str, outcome: str, support_ids: list[str]) -> str:
    if section.lower() in {"evidence", "verification", "sources", "checks", "trace"}:
        return _compact_support_text(support_ids)
    if "next step" in section.lower():
        return _compact_next_step(outcome)
    return compact


def _compact_next_step(outcome: str) -> str:
    return {
        "accepted_candidate": "Continue the supported path.",
        "blocked_policy": "Provide approval or change the action.",
        "repair_evidence": "Provide a supporting source.",
        "repair_conflict": "Resolve the conflicting constraint.",
        "repair_clarify": "Name the exact target.",
    }[outcome]


def _fidelity_errors(lowered: str, outcome: str) -> list[str]:
    if outcome == "blocked_policy" and not any(word in lowered for word in ("blocked", "cannot", "deny")):
        return ["outcome_policy_missing"]
    if outcome == "repair_evidence" and "evidence" not in lowered and "source" not in lowered:
        return ["outcome_evidence_missing"]
    if outcome == "repair_conflict" and "conflict" not in lowered and "resolution" not in lowered:
        return ["outcome_conflict_missing"]
    if outcome == "repair_clarify" and "clarif" not in lowered and "target" not in lowered and "reference" not in lowered:
        return ["outcome_clarify_missing"]
    if outcome == "accepted_candidate" and "accept" not in lowered and "selected" not in lowered:
        return ["outcome_accept_missing"]
    return []


def _profile_errors(data: dict[str, Any]) -> list[str]:
    errors = []
    if set(data) - PROFILE_KEYS:
        errors.append("unknown_profile_fields")
    if data.get("style") not in {"balanced", "concise", "evidence_first", "direct", "repair", "coding"}:
        errors.append("invalid_style")
    if not isinstance(data.get("max_chars"), int) or not 80 <= data["max_chars"] <= MAX_OUTPUT_CHARS:
        errors.append("invalid_max_chars")
    sections = data.get("required_sections")
    if not isinstance(sections, list) or len(sections) > MAX_SECTIONS or any(not isinstance(item, str) or not item.strip() for item in sections):
        errors.append("invalid_sections")
    elif any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,31}", item) for item in sections):
        errors.append("invalid_section_grammar")
    forbidden = data.get("forbidden_phrases")
    if not isinstance(forbidden, list) or any(not isinstance(item, str) or not 1 <= len(item.strip()) <= 80 for item in (forbidden or [])):
        errors.append("invalid_forbidden_phrases")
    elif any(item.strip().lower() in PROTECTED_FIDELITY_TERMS for item in forbidden):
        errors.append("protected_fidelity_term_forbidden")
    for key in ("require_support_refs", "include_next_step"):
        if not isinstance(data.get(key), bool):
            errors.append(f"invalid_{key}")
    if isinstance(sections, list) and isinstance(data.get("max_chars"), int):
        minimum = sum(len(item) + 4 for item in sections)
        minimum += 28 if data.get("require_support_refs") else 0
        minimum += 24 if data.get("include_next_step") else 0
        if minimum > data["max_chars"]:
            errors.append("infeasible_profile_budget")
    return errors


def _response_chunks(response: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"chunk_id": f"out-{index:02d}", "role": "rendered_section", "seed": stable_seed(line, salt="lce-renderer-v5"), "text": line}
        for index, line in enumerate(response.splitlines(), start=1)
    ]


def _ratio(values: Any) -> float:
    rows = list(values)
    return round(sum(1 for value in rows if value) / len(rows), 6) if rows else 1.0


def _mean(values: Any) -> float:
    rows = list(values)
    return round(sum(rows) / len(rows), 6) if rows else 0.0


def _by_tag(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
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
