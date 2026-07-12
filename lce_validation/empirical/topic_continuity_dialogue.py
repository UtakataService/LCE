from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .history_chunked_dialogue import respond_with_history_chunks
from .nl_normalization import normalize_tokens
from .seeded_dialogue import stable_seed


TOPIC_OUTPUT = {
    "topic_continue": [
        "Continue the existing topic and reuse the accepted history chunks.",
        "Carry the prior topic forward and constrain the answer with the history state.",
    ],
    "topic_shift": [
        "Treat this as an explicit topic shift and start a new local chunk branch.",
        "Start a new topic branch while keeping the previous state available for reference.",
    ],
    "contradiction_repair": [
        "The current input conflicts with accepted history, so repair is required before composing a normal answer.",
        "A contradiction was detected against the carried state; ask for resolution instead of silently switching.",
    ],
    "no_history": [
        "No history is available, so the response starts from the current input chunks only.",
        "This turn has no carried state; build the response from the current chunk graph.",
    ],
}


def respond_with_topic_continuity(current_input: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    base = respond_with_history_chunks(current_input, history or [])
    topic = evaluate_topic_relation(base["history_chunks"], base["current_chunks"], current_input)
    output_chunks = build_topic_output_chunks(base, topic)
    coherence = check_topic_coherence(base, topic, output_chunks)
    response = " ".join(chunk["text"] for chunk in output_chunks)
    return {
        "ok": coherence["ok"],
        "current_input": current_input,
        "history_turn_count": base["history_turn_count"],
        "topic_relation": topic,
        "base_route": base["route"],
        "route": route_from_topic(base["route"], topic),
        "history_chunks": base["history_chunks"],
        "current_chunks": base["current_chunks"],
        "output_chunks": output_chunks,
        "response": response,
        "coherence": coherence,
        "claim": "bounded_topic_continuity_dialogue_control_only",
        "blocked_claims": [
            "open_domain_conversation",
            "general_language_understanding",
            "deep_contradiction_reasoning",
            "long_term_memory",
            "llm_quality_parity",
            "transformer_replacement",
        ],
    }


def evaluate_topic_relation(
    history_chunks: list[dict[str, Any]],
    current_chunks: list[dict[str, Any]],
    current_input: str,
) -> dict[str, Any]:
    history_text = " ".join(chunk["text"] for chunk in history_chunks).lower()
    current_text = current_input.lower()
    history_tokens = set(_tokens_from_chunks(history_chunks))
    current_tokens = set(_tokens_from_chunks(current_chunks))
    overlap = sorted(history_tokens & current_tokens)

    contradiction = detect_contradiction(history_text, current_text)
    if contradiction:
        return {
            "status": "contradiction_repair",
            "reason": contradiction,
            "token_overlap": overlap,
            "overlap_count": len(overlap),
        }

    if not history_chunks:
        return {
            "status": "no_history",
            "reason": "no history chunks are available",
            "token_overlap": [],
            "overlap_count": 0,
        }

    if _has_topic_shift_marker(current_text):
        return {
            "status": "topic_shift",
            "reason": "explicit topic shift marker detected",
            "token_overlap": overlap,
            "overlap_count": len(overlap),
        }

    if overlap or _has_continuation_marker(current_text):
        return {
            "status": "topic_continue",
            "reason": "current input overlaps with or refers to the carried topic",
            "token_overlap": overlap,
            "overlap_count": len(overlap),
        }

    return {
        "status": "topic_shift",
        "reason": "no useful overlap with carried topic",
        "token_overlap": overlap,
        "overlap_count": len(overlap),
    }


def detect_contradiction(history_text: str, current_text: str) -> str | None:
    if "safety" in history_text and "deterministic" in history_text:
        if "random" in current_text and ("safety" in current_text or "gate" in current_text):
            return "current input asks to randomize a safety gate that history fixed as deterministic"
    if "\u5b89\u5168" in history_text and "\u6c7a\u5b9a\u7684" in history_text:
        if "\u30e9\u30f3\u30c0\u30e0" in current_text and "\u30b2\u30fc\u30c8" in current_text:
            return "current input asks to randomize a safety gate that history fixed as deterministic"
    if "english" in history_text and ("primary" in history_text or "main lane" in history_text):
        japanese_primary = "japanese" in current_text and ("primary" in current_text or "main" in current_text)
        ignores_english = "ignore english" in current_text or "not english" in current_text
        if japanese_primary and ignores_english:
            return "current input contradicts the accepted English-primary language scope"
    if "do not delete" in history_text and "delete" in current_text and "without approval" in current_text:
        return "current input contradicts a prior delete-without-approval prohibition"
    return None


def build_topic_output_chunks(base: dict[str, Any], topic: dict[str, Any]) -> list[dict[str, Any]]:
    seed_basis = json.dumps(
        {
            "route": base["route"],
            "topic": topic,
            "current": base["current_input"],
        },
        ensure_ascii=False,
    )
    rng = random.Random(stable_seed(seed_basis, salt="lce-topic-output-v0"))
    status = topic["status"]
    output = [
        _out("out-01", "ack", "Topic continuity check complete.", stable_seed(seed_basis, salt="lce-topic-ack-v0")),
        _out("out-02", status, rng.choice(TOPIC_OUTPUT[status]), stable_seed(f"{status}:{seed_basis}", salt="lce-topic-status-v0")),
    ]
    if base["route"] in {"deny", "require_evidence", "ask_confirmation"}:
        output.append(_out("out-03", "gate", "Policy gates remain stronger than topic continuity.", stable_seed(seed_basis, salt="lce-topic-gate-v0")))
        return output
    if status == "contradiction_repair":
        output.append(_out("out-03", "repair", f"Repair reason: {topic['reason']}.", stable_seed(seed_basis, salt="lce-topic-repair-v0")))
        return output
    if status == "topic_shift":
        output.append(_out("out-03", "new_branch", "Create a fresh local topic branch and keep older chunks as reference only.", stable_seed(seed_basis, salt="lce-topic-branch-v0")))
        return output
    output.append(_out("out-03", "compose", "Compose the answer from current chunks plus relevant carried history chunks.", stable_seed(seed_basis, salt="lce-topic-compose-v0")))
    return output


def check_topic_coherence(base: dict[str, Any], topic: dict[str, Any], output_chunks: list[dict[str, Any]]) -> dict[str, Any]:
    roles = [chunk["role"] for chunk in output_chunks]
    errors: list[str] = []
    if roles[0] != "ack":
        errors.append("missing_ack_first")
    if topic["status"] not in roles:
        errors.append("missing_topic_status_output")
    if topic["status"] == "contradiction_repair" and "repair" not in roles:
        errors.append("missing_repair_output")
    if topic["status"] == "topic_shift" and "new_branch" not in roles:
        errors.append("missing_new_branch_output")
    if base["route"] in {"deny", "require_evidence", "ask_confirmation"} and "gate" not in roles:
        errors.append("missing_policy_gate_output")
    return {
        "ok": not errors,
        "errors": errors,
        "topic_status": topic["status"],
        "output_chunk_count": len(output_chunks),
    }


def run_topic_continuity_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case in load_jsonl(cases_path):
        result = respond_with_topic_continuity(case["current_input"], case.get("history", []))
        repeat = respond_with_topic_continuity(case["current_input"], case.get("history", []))
        status_ok = result["topic_relation"]["status"] == case["expected_topic_status"]
        route_ok = result["route"] == case["expected_route"]
        coherence_ok = result["coherence"]["ok"] == case["expected_coherence_ok"]
        deterministic = result == repeat
        rows.append({
            "case_id": case["case_id"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "expected_topic_status": case["expected_topic_status"],
            "actual_topic_status": result["topic_relation"]["status"],
            "expected_route": case["expected_route"],
            "actual_route": result["route"],
            "status_ok": status_ok,
            "route_ok": route_ok,
            "coherence_ok": coherence_ok,
            "deterministic": deterministic,
            "case_ok": status_ok and route_ok and coherence_ok and deterministic,
            "result": result,
        })
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "topic_status_accuracy": _ratio(row["status_ok"] for row in rows),
        "route_accuracy": _ratio(row["route_ok"] for row in rows),
        "coherence_accuracy": _ratio(row["coherence_ok"] for row in rows),
        "determinism_accuracy": _ratio(row["deterministic"] for row in rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "by_tag": _by_tag(rows),
        "claim": "bounded_topic_continuity_dialogue_control_only",
        "blocked_claims": [
            "open_domain_conversation",
            "general_language_understanding",
            "deep_contradiction_reasoning",
            "long_term_memory",
            "llm_quality_parity",
            "transformer_replacement",
        ],
    }
    _write_jsonl(out / "topic_continuity_rows.jsonl", rows)
    (out / "topic_continuity_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def route_from_topic(base_route: str, topic: dict[str, Any]) -> str:
    if base_route in {"deny", "require_evidence", "ask_confirmation"}:
        return base_route
    if topic["status"] == "contradiction_repair":
        return "contradiction_repair"
    if topic["status"] == "topic_shift":
        return "topic_shift"
    if topic["status"] == "topic_continue":
        return "topic_continue"
    return base_route


def _tokens_from_chunks(chunks: list[dict[str, Any]]) -> list[str]:
    tokens: list[str] = []
    for chunk in chunks:
        tokens.extend(normalize_tokens(chunk["text"]))
    return [token for token in tokens if token not in {"with", "from", "into", "then", "than"}]


def _has_topic_shift_marker(text: str) -> bool:
    markers = ["switch topic", "new topic", "instead discuss", "now discuss", "change topic", "別の話題", "話題を変"]
    return any(marker in text for marker in markers)


def _has_continuation_marker(text: str) -> bool:
    markers = ["continue", "keep going", "same topic", "that plan", "this approach", "引き続き", "続け"]
    return any(marker in text for marker in markers)


def _out(chunk_id: str, role: str, text: str, seed: int) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "role": role,
        "seed": seed,
        "text": text,
    }


def _ratio(values: Any) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return round(sum(1 for value in vals if value) / len(vals), 6)


def _by_tag(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        for tag in row["phenomenon_tags"]:
            entry = result.setdefault(tag, {"case_count": 0, "case_ok": 0})
            entry["case_count"] += 1
            entry["case_ok"] += 1 if row["case_ok"] else 0
    for entry in result.values():
        entry["accuracy"] = round(entry["case_ok"] / entry["case_count"], 6)
    return result


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
