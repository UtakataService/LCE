"""Deterministic, inspectable routing for the bounded LCE runtime modes."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ModeDecision:
    mode: str
    confidence: float
    reasons: tuple[str, ...]


def select_mode(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text", "")).casefold()
    history = payload.get("history", [])
    if payload.get("schema") is not None or payload.get("data") is not None or any(token in text for token in ("json", "schema", "valid json", "jsonで", "構造出力")):
        return asdict(ModeDecision("structured", 0.98, ("structured_contract_signal",)))
    if any(token in text for token in ("kill myself", "suicide", "self harm", "hurt myself", "自分を傷つけ", "今夜を乗り切れ", "暗証番号", "パスワード")):
        return asdict(ModeDecision("daily_dialogue", 0.99, ("safety_boundary_signal",)))
    if any(token in text for token in ("def ", "function ", "python", "typescript", "write code", "コードを書", "関数を")):
        return asdict(ModeDecision("coding", 0.90, ("bounded_coding_signal",)))
    if len(history) >= 2 and any(token in text for token in ("go back", "return to", "actually", "correction", "前の話", "訂正")):
        return asdict(ModeDecision("daily_dialogue", 0.84, ("stateful_dialogue_signal",)))
    if any(token in text for token in ("compare", "versus", "pros and cons", "a and b", "比較", "それぞれ")):
        return asdict(ModeDecision("layered_reasoning", 0.72, ("multi_aspect_reasoning_signal",)))
    return asdict(ModeDecision("daily_dialogue", 0.55, ("safe_default_daily_dialogue",)))
