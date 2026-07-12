from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .chunked_dialogue import (
    analyze_chunk,
    check_output_coherence,
    chunk_input,
    route_from_chunks,
    strongest_decision,
)
from .engine import load_jsonl
from .policy_pack_lifecycle import evaluate_policy_pack
from .seeded_dialogue import DEFAULT_POLICY_PACK, build_action, infer_dialogue_signal, stable_seed


HISTORY_ACK = [
    "I will carry the recent context forward.",
    "The previous turns are now part of the response state.",
    "I will treat the current input as a continuation, not an isolated prompt.",
]

HISTORY_PLANS = {
    "continuity": [
        "The answer should preserve the prior topic unless the current input explicitly changes it.",
        "History chunks constrain the current response so it does not restart from scratch.",
    ],
    "chunk_seed": [
        "Each history turn and current input chunk receives a stable seed at a chunk-sized granularity.",
        "The state is built from chunk seeds, not token-level sampling.",
    ],
    "compose": [
        "Output chunks are composed after checking history, current intent, and policy gates.",
        "The response is assembled from reusable output chunks and then checked for coherence.",
    ],
    "japanese_eval": [
        "Japanese evaluation inputs are treated as coverage checks, while English remains the primary lane.",
        "Japanese is included lightly for evaluation, but the main behavior is English-first.",
    ],
    "next": [
        "The next step is to add topic carryover tests and contradiction repair.",
        "After this, the system should learn to detect topic shifts and unresolved references.",
    ],
}

GATE_TEXT = {
    "DENY": "A policy gate blocks execution, so the response must not include an execution plan.",
    "REQUIRE_EVIDENCE": "The current state requires evidence before making a factual answer.",
    "ASK_CONFIRMATION": "The current state requires confirmation before execution.",
    "CONFLICT": "The current policy state is conflicting, so the response must ask for resolution.",
}


def respond_with_history_chunks(
    current_input: str,
    history: list[dict[str, str]] | None = None,
    policy_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    history = history or []
    pack = policy_pack or DEFAULT_POLICY_PACK
    history_chunks = build_history_chunks(history, pack)
    current_chunks = [analyze_chunk(chunk, pack) for chunk in chunk_input(current_input)]
    all_chunks = history_chunks + current_chunks
    output_chunks = build_history_output_chunks(current_input, history_chunks, current_chunks)
    coherence = check_history_coherence(history_chunks, current_chunks, output_chunks)
    route = route_from_history(history_chunks, current_chunks)
    return {
        "ok": coherence["ok"],
        "current_input": current_input,
        "history_turn_count": len(history),
        "global_seed": stable_seed(json.dumps({"history": history, "input": current_input}, ensure_ascii=False), salt="lce-history-chunked-global-v0"),
        "history_chunks": history_chunks,
        "current_chunks": current_chunks,
        "all_chunk_count": len(all_chunks),
        "output_chunks": output_chunks,
        "response": " ".join(chunk["text"] for chunk in output_chunks),
        "route": route,
        "coherence": coherence,
        "claim": "bounded_history_chunked_dialogue_control_only",
        "blocked_claims": [
            "open_domain_conversation",
            "general_language_understanding",
            "long_context_reasoning",
            "memory_learning",
            "llm_quality_parity",
            "transformer_replacement",
        ],
    }


def build_history_chunks(history: list[dict[str, str]], policy_pack: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for turn_index, turn in enumerate(history[-4:]):
        # Accept the dialogue-runtime convention as well as the original
        # history-chunk convention; both are read-only history aliases.
        speaker = turn.get("speaker", turn.get("role", "unknown"))
        text = turn.get("text", turn.get("content", ""))
        for local_chunk in chunk_input(text):
            chunk = dict(local_chunk)
            chunk["chunk_id"] = f"h{turn_index + 1:02d}-{local_chunk['chunk_id']}"
            chunk["speaker"] = speaker
            chunk["turn_index"] = turn_index
            chunk["seed"] = stable_seed(f"{speaker}:{turn_index}:{local_chunk['text']}", salt="lce-history-chunk-v0")
            analyzed = analyze_history_chunk(chunk, policy_pack)
            chunks.append(analyzed)
    return chunks


def analyze_history_chunk(chunk: dict[str, Any], policy_pack: dict[str, Any]) -> dict[str, Any]:
    rng = random.Random(chunk["seed"])
    signal = infer_dialogue_signal(chunk["text"], rng)
    action = build_action(signal)
    policy = evaluate_policy_pack(policy_pack, action)
    role = classify_history_role(chunk["text"], signal)
    result = dict(chunk)
    result.update({
        "semantic_role": role,
        "signal": signal,
        "action": action,
        "policy_decision": policy["decision"],
        "policy_reason": policy["reason"],
    })
    return result


def build_history_output_chunks(
    current_input: str,
    history_chunks: list[dict[str, Any]],
    current_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seed_basis = json.dumps(
        {
            "history": [(chunk["speaker"], chunk["text"], chunk["semantic_role"]) for chunk in history_chunks],
            "current": [(chunk["text"], chunk["semantic_role"]) for chunk in current_chunks],
        },
        ensure_ascii=False,
    )
    global_seed = stable_seed(seed_basis, salt="lce-history-output-v0")
    rng = random.Random(global_seed)
    output = [_out("out-01", "ack", rng.choice(HISTORY_ACK), global_seed)]

    blocking = [chunk for chunk in history_chunks + current_chunks if chunk["policy_decision"] in GATE_TEXT]
    if blocking:
        decision = strongest_decision([chunk["policy_decision"] for chunk in blocking])
        output.append(_out("out-02", "gate", GATE_TEXT[decision], stable_seed(decision, salt="lce-history-gate-v0")))
        output.append(_out("out-03", "next_step", "Resolve the gate first, then rebuild the chunk response.", stable_seed(current_input, salt="lce-history-gate-next-v0")))
        return output

    roles = {chunk["semantic_role"] for chunk in history_chunks + current_chunks}
    keys = ["continuity"]
    if "chunk_seed" in roles:
        keys.append("chunk_seed")
    if "composition" in roles or "implementation" in roles:
        keys.append("compose")
    if any(chunk.get("language_hint") == "ja" for chunk in history_chunks + current_chunks):
        keys.append("japanese_eval")
    keys.append("next")

    for index, key in enumerate(dict.fromkeys(keys), start=2):
        seed = stable_seed(f"{key}:{seed_basis}", salt="lce-history-output-plan-v0")
        text = random.Random(seed).choice(HISTORY_PLANS[key])
        output.append(_out(f"out-{index:02d}", key, text, seed))
    return output


def check_history_coherence(
    history_chunks: list[dict[str, Any]],
    current_chunks: list[dict[str, Any]],
    output_chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    base = check_output_coherence(history_chunks + current_chunks, output_chunks)
    errors = list(base["errors"])
    roles = [chunk["role"] for chunk in output_chunks]
    if history_chunks and "continuity" not in roles and "gate" not in roles:
        errors.append("missing_history_continuity_output")
    if any(chunk["policy_decision"] == "DENY" for chunk in history_chunks + current_chunks) and "gate" not in roles:
        errors.append("missing_history_gate_output")
    return {
        "ok": not errors,
        "errors": errors,
        "history_chunk_count": len(history_chunks),
        "current_chunk_count": len(current_chunks),
        "output_chunk_count": len(output_chunks),
    }


def run_history_chunked_dialogue_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case in load_jsonl(cases_path):
        result = respond_with_history_chunks(case["current_input"], case.get("history", []))
        repeat = respond_with_history_chunks(case["current_input"], case.get("history", []))
        route_ok = result["route"] == case["expected_route"]
        coherence_ok = result["coherence"]["ok"] == case["expected_coherence_ok"]
        deterministic = result == repeat
        min_history_ok = len(result["history_chunks"]) >= case.get("min_history_chunks", 0)
        rows.append({
            "case_id": case["case_id"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "expected_route": case["expected_route"],
            "actual_route": result["route"],
            "route_ok": route_ok,
            "coherence_ok": coherence_ok,
            "deterministic": deterministic,
            "min_history_ok": min_history_ok,
            "case_ok": route_ok and coherence_ok and deterministic and min_history_ok,
            "result": result,
        })
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "route_accuracy": _ratio(row["route_ok"] for row in rows),
        "coherence_accuracy": _ratio(row["coherence_ok"] for row in rows),
        "determinism_accuracy": _ratio(row["deterministic"] for row in rows),
        "history_chunk_accuracy": _ratio(row["min_history_ok"] for row in rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "by_tag": _by_tag(rows),
        "claim": "bounded_history_chunked_dialogue_control_only",
        "blocked_claims": [
            "open_domain_conversation",
            "general_language_understanding",
            "long_context_reasoning",
            "memory_learning",
            "llm_quality_parity",
            "transformer_replacement",
        ],
    }
    _write_jsonl(out / "history_chunked_dialogue_rows.jsonl", rows)
    (out / "history_chunked_dialogue_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def route_from_history(history_chunks: list[dict[str, Any]], current_chunks: list[dict[str, Any]]) -> str:
    route = route_from_chunks(history_chunks + current_chunks)
    if route in {"deny", "require_evidence", "ask_confirmation", "clarify"}:
        return route
    if history_chunks:
        return "history_chunk_plan"
    return route


def classify_history_role(text: str, signal: dict[str, Any]) -> str:
    lowered = text.lower()
    if "seed" in lowered or "chunk" in lowered:
        return "chunk_seed"
    if "combine" in lowered or "compose" in lowered or "coherent" in lowered or "consistency" in lowered:
        return "composition"
    if "english" in lowered or "language" in lowered:
        return "language_scope"
    if any("\u3040" <= char <= "\u30ff" or "\u4e00" <= char <= "\u9fff" for char in text):
        return "language_scope"
    if signal["intent"] == "continue_task":
        return "implementation"
    return "context"


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
