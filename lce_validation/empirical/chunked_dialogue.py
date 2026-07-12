from __future__ import annotations

import json
import re
import random
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .policy_pack_lifecycle import evaluate_policy_pack
from .seeded_dialogue import DEFAULT_POLICY_PACK, build_action, infer_dialogue_signal, stable_seed


ACK_TEMPLATES = [
    "考え方は合っています。",
    "その方向で進められます。",
    "かなり実装向きの分解です。",
]

PLAN_TEMPLATES = {
    "chunk_seed": [
        "入力を意味チャンクに分け、各チャンクに安定seedを割り当てます。",
        "tokenより大きい単位で入力を分割し、chunk seedとして保持します。",
    ],
    "compose": [
        "出力もチャンク単位で作り、最後に順序と矛盾を検査します。",
        "返答は複数の出力チャンクを組み合わせ、整合チェックを通して確定します。",
    ],
    "safety": [
        "安全ゲートはseedで揺らさず、policy packの判定を優先します。",
        "拒否や確認要求はランダム化せず、固定ルールで決めます。",
    ],
    "next": [
        "次は短い会話履歴もchunk seedに混ぜると、状態つき対話に進めます。",
        "この後は2から4 turn程度の履歴をchunk graphに入れるのが自然です。",
    ],
}

GATE_TEMPLATES = {
    "DENY": "この入力には禁止ゲートが含まれるため、実行系の出力チャンクは止めます。",
    "REQUIRE_EVIDENCE": "根拠要求チャンクがあるため、断定ではなく証拠要求として返します。",
    "ASK_CONFIRMATION": "確認要求チャンクがあるため、実行前確認を出力に含めます。",
    "CONFLICT": "同じ優先度のルール衝突があるため、判断を確定せず保留します。",
}


def respond_from_chunk_seeds(user_input: str, policy_pack: dict[str, Any] | None = None) -> dict[str, Any]:
    input_chunks = chunk_input(user_input)
    pack = policy_pack or DEFAULT_POLICY_PACK
    analyzed = [analyze_chunk(chunk, pack) for chunk in input_chunks]
    output_chunks = build_output_chunks(user_input, analyzed)
    coherence = check_output_coherence(analyzed, output_chunks)
    return {
        "ok": coherence["ok"],
        "input": user_input,
        "global_seed": stable_seed(user_input, salt="lce-chunked-dialogue-global-v0"),
        "input_chunks": analyzed,
        "output_chunks": output_chunks,
        "response": "".join(chunk["text"] for chunk in output_chunks),
        "coherence": coherence,
        "route": route_from_chunks(analyzed),
        "claim": "bounded_chunk_seeded_dialogue_control_only",
        "blocked_claims": [
            "open_domain_conversation",
            "general_language_understanding",
            "semantic_embedding_replacement",
            "llm_quality_parity",
            "transformer_replacement",
        ],
    }


def chunk_input(user_input: str) -> list[dict[str, Any]]:
    parts = [part.strip() for part in re.split(r"[。．.!?,\n]+|(?:\s+and\s+)|(?:\s+but\s+)|(?:、)", user_input) if part.strip()]
    if not parts:
        parts = [user_input.strip()]
    if len(parts) == 1 and len(parts[0]) > 28:
        parts = _split_long_part(parts[0])
    chunks = []
    for index, text in enumerate(parts):
        seed = stable_seed(text, salt=f"lce-input-chunk-v0:{index}")
        chunks.append({
            "chunk_id": f"in-{index + 1:02d}",
            "text": text,
            "seed": seed,
            "size": len(text),
        })
    return chunks


def analyze_chunk(chunk: dict[str, Any], policy_pack: dict[str, Any]) -> dict[str, Any]:
    rng = random.Random(chunk["seed"])
    signal = infer_dialogue_signal(chunk["text"], rng)
    action = build_action(signal)
    policy = evaluate_policy_pack(policy_pack, action)
    semantic_role = classify_semantic_role(chunk["text"], signal, policy)
    result = dict(chunk)
    result.update({
        "semantic_role": semantic_role,
        "signal": signal,
        "action": action,
        "policy_decision": policy["decision"],
        "policy_reason": policy["reason"],
    })
    return result


def build_output_chunks(user_input: str, analyzed_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    global_seed = stable_seed(user_input, salt="lce-output-chunk-v0")
    rng = random.Random(global_seed)
    route = route_from_chunks(analyzed_chunks)
    chunks: list[dict[str, Any]] = []
    chunks.append(_out("out-01", "ack", rng.choice(ACK_TEMPLATES), global_seed))

    blocking = [chunk for chunk in analyzed_chunks if chunk["policy_decision"] in GATE_TEMPLATES]
    if blocking:
        decision = strongest_decision([chunk["policy_decision"] for chunk in blocking])
        chunks.append(_out("out-02", "gate", GATE_TEMPLATES[decision], stable_seed(decision, salt="lce-output-gate-v0")))
        chunks.append(_out("out-03", "next_step", "対象を限定するか、承認・証拠・確認を追加してから再評価します。", stable_seed(route, salt="lce-output-next-v0")))
        return chunks

    roles = {chunk["semantic_role"] for chunk in analyzed_chunks}
    plan_keys = []
    if "chunk_seed" in roles:
        plan_keys.append("chunk_seed")
    if "composition" in roles or "implementation" in roles:
        plan_keys.append("compose")
    plan_keys.append("safety")
    plan_keys.append("next")

    for offset, key in enumerate(dict.fromkeys(plan_keys), start=2):
        seed = stable_seed(f"{key}:{user_input}", salt="lce-output-plan-v0")
        text = random.Random(seed).choice(PLAN_TEMPLATES[key])
        chunks.append(_out(f"out-{offset:02d}", key, text, seed))
    return chunks


def check_output_coherence(input_chunks: list[dict[str, Any]], output_chunks: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    decisions = {chunk["policy_decision"] for chunk in input_chunks}
    output_roles = [chunk["role"] for chunk in output_chunks]
    if "DENY" in decisions and "gate" not in output_roles:
        errors.append("missing_gate_output_for_deny")
    if "REQUIRE_EVIDENCE" in decisions and "gate" not in output_roles:
        errors.append("missing_gate_output_for_evidence")
    if "gate" in output_roles and any(role in output_roles for role in ("chunk_seed", "compose")):
        errors.append("unsafe_plan_after_gate")
    if output_roles[0] != "ack":
        errors.append("missing_ack_first")
    return {
        "ok": not errors,
        "errors": errors,
        "input_chunk_count": len(input_chunks),
        "output_chunk_count": len(output_chunks),
    }


def run_chunked_dialogue_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case in load_jsonl(cases_path):
        result = respond_from_chunk_seeds(case["input"])
        repeat = respond_from_chunk_seeds(case["input"])
        route_ok = result["route"] == case["expected_route"]
        coherence_ok = result["coherence"]["ok"] == case["expected_coherence_ok"]
        deterministic = result == repeat
        min_chunks_ok = len(result["input_chunks"]) >= case.get("min_input_chunks", 1)
        rows.append({
            "case_id": case["case_id"],
            "input": case["input"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "expected_route": case["expected_route"],
            "actual_route": result["route"],
            "route_ok": route_ok,
            "coherence_ok": coherence_ok,
            "deterministic": deterministic,
            "min_chunks_ok": min_chunks_ok,
            "case_ok": route_ok and coherence_ok and deterministic and min_chunks_ok,
            "result": result,
        })
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "route_accuracy": _ratio(row["route_ok"] for row in rows),
        "coherence_accuracy": _ratio(row["coherence_ok"] for row in rows),
        "determinism_accuracy": _ratio(row["deterministic"] for row in rows),
        "chunking_accuracy": _ratio(row["min_chunks_ok"] for row in rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "by_tag": _by_tag(rows),
        "claim": "bounded_chunk_seeded_dialogue_control_only",
        "blocked_claims": [
            "open_domain_conversation",
            "general_language_understanding",
            "semantic_embedding_replacement",
            "llm_quality_parity",
            "transformer_replacement",
        ],
    }
    _write_jsonl(out / "chunked_dialogue_rows.jsonl", rows)
    (out / "chunked_dialogue_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def classify_semantic_role(text: str, signal: dict[str, Any], policy: dict[str, Any]) -> str:
    lowered = text.lower()
    if policy["decision"] in GATE_TEMPLATES:
        return "safety_gate"
    if "seed" in lowered or "シード" in lowered:
        return "chunk_seed"
    if "chunk" in lowered or "チャンク" in lowered:
        return "chunk_seed"
    if "combine" in lowered or "compose" in lowered or "組み合わせ" in lowered or "整合" in lowered:
        return "composition"
    if signal["intent"] == "continue_task":
        return "implementation"
    if signal["intent"] == "clarify_intent":
        return "clarification"
    return "context"


def route_from_chunks(chunks: list[dict[str, Any]]) -> str:
    decisions = [chunk["policy_decision"] for chunk in chunks]
    if "DENY" in decisions:
        return "deny"
    if "REQUIRE_EVIDENCE" in decisions:
        return "require_evidence"
    if "ASK_CONFIRMATION" in decisions:
        return "ask_confirmation"
    if "CONFLICT" in decisions:
        return "clarify"
    roles = {chunk["semantic_role"] for chunk in chunks}
    if "chunk_seed" in roles or "composition" in roles:
        return "chunk_plan"
    return "continue"


def strongest_decision(decisions: list[str]) -> str:
    order = {"DENY": 100, "CONFLICT": 90, "REQUIRE_EVIDENCE": 80, "ASK_CONFIRMATION": 70}
    return sorted(decisions, key=lambda item: order.get(item, 0), reverse=True)[0]


def _out(chunk_id: str, role: str, text: str, seed: int) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "role": role,
        "seed": seed,
        "text": text,
    }


def _split_long_part(text: str, max_chars: int = 48) -> list[str]:
    if re.search(r"\s", text):
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for word in text.split():
            projected = current_len + len(word) + (1 if current else 0)
            if current and projected > max_chars:
                chunks.append(" ".join(current))
                current = [word]
                current_len = len(word)
            else:
                current.append(word)
                current_len = projected
        if current:
            chunks.append(" ".join(current))
        return chunks
    return [text[index:index + 24].strip() for index in range(0, len(text), 24) if text[index:index + 24].strip()]


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
