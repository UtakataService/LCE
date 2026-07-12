"""Bounded structural features for a single dialogue turn.

The active recognizer reads the versioned Reference LanguagePack.  The legacy
table remains only as a dual-run comparator during Open Core migration.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
import re
from typing import Literal

from .model_pack import load_pack, recognize_language_pack
from .runtime_profile import RuntimeProfile, reference_runtime_profile
from .semantic_events import classify_semantic_events
from .semantic_space import resolve_semantic_units


REFERENCE_FRAME_PACK_PATH = Path(__file__).parents[1] / "fixtures" / "reference_language_pack_frame_v1.json"

# Frozen comparator, not the active recognition source.
_LEGACY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("reports_difficulty", ("rough day", "stressed", "tired", "\u75b2\u308c", "\u56f0\u3063\u3066")),
    ("advice_permitted", ("open to", "a few ideas", "\u9078\u629e\u80a2", "\u63d0\u6848\u3057\u3066")),
    ("repair", ("actually", "i meant", "correction", "訂正", "そういう意味じゃない", "違う、")),
    ("negate", ("not really", "no,", "don't", "without", "違う", "いや", "いらない")),
    ("close", ("bye", "talk later", "for today", "今日はここまで", "また今度", "じゃあね")),
    ("return", ("return to", "back to", "earlier", "前の話", "さっきの話", "戻る")),
    ("shift", ("by the way", "another note", "something else", "ところで", "別の話", "そういえば")),
    ("listen_only", ("just listen", "hear me out", "without advice", "聞いてほしい", "愚痴", "解決策はいらない")),
    ("advice_request", ("what should", "advice", "help me decide", "どうすれば", "意見がほしい")),
    ("acknowledge", ("got it", "makes sense", "i see", "なるほど", "たしかに", "分かった")),
    ("difficulty", ("stressed", "overwhelmed", "exhausted", "frustrated", "疲れ", "しんど", "困っ", "イライラ")),
    ("ambiguous_reference", ("former", "latter", "that one", "前者", "後者", "それ")),
    ("explicit_reference", ("is called", "means", "とは", "という")),
    ("question_form", ("what is", "what are", "how do", "なに", "何？")),
)


@dataclass(frozen=True, slots=True)
class UtteranceFrame:
    language: Literal["en", "ja", "mixed"]
    sentence_type: Literal["question", "statement", "fragment"]
    polarity: Literal["affirm", "negate", "repair", "unknown"]
    discourse: Literal["continue", "shift", "return", "close", "unknown"]
    interpersonal: Literal["listen_only", "advice_request", "acknowledge", "share_difficulty", "unknown"]
    reference: Literal["explicit", "ambiguous", "none"]
    cues: tuple[str, ...]
    legacy_rule_ids: tuple[str, ...]
    semantic_ids: tuple[str, ...]
    semantic_units: tuple[dict[str, object], ...]
    unmapped_semantic_labels: tuple[str, ...]


def frame_utterance(text: str, *, runtime_profile: RuntimeProfile | None = None) -> dict[str, object]:
    profile = runtime_profile or reference_runtime_profile()
    cues, rule_ids = _recognized_labels(text, profile)
    return _build_frame(text, cues, rule_ids, semantic_cube=profile.semantic_cube_pack, runtime_identity=profile.trace_identity())


def frame_utterance_legacy(text: str, *, runtime_profile: RuntimeProfile | None = None) -> dict[str, object]:
    """Frozen source comparator for Reference Pack parity tests only."""
    lowered = text.casefold()
    cues = [label for label, patterns in _LEGACY_RULES if any(pattern in lowered for pattern in patterns)]
    rule_ids = [f"legacy.frame.{label}.v1" for label in cues]
    profile = runtime_profile or reference_runtime_profile()
    signal_cues, signal_rule_ids = _recognized_signal_labels(text, profile)
    return _build_frame(text, cues + signal_cues, rule_ids + signal_rule_ids, semantic_cube=profile.semantic_cube_pack, runtime_identity=profile.trace_identity())


@lru_cache(maxsize=1)
def _reference_frame_pack() -> dict[str, object]:
    return load_pack(REFERENCE_FRAME_PACK_PATH)


def _build_frame(text: str, raw_cues: list[str], raw_rule_ids: list[str], *, semantic_cube: dict[str, object], runtime_identity: dict[str, object]) -> dict[str, object]:
    lowered = text.casefold().strip()
    ja = any(ord(char) > 127 for char in text)
    en = bool(re.search(r"[a-z]", lowered))
    language = "mixed" if ja and en else ("ja" if ja else "en")
    cues = tuple(raw_cues)
    semantic = resolve_semantic_units(raw_cues, raw_rule_ids, semantic_cube=semantic_cube)
    has = set(cues).__contains__
    question = lowered.endswith("?") or "？" in text or has("question_form")
    frame = UtteranceFrame(
        language=language,
        sentence_type="question" if question else ("fragment" if len(lowered.split()) < 3 and not ja else "statement"),
        polarity="repair" if has("repair") else ("negate" if has("negate") else ("affirm" if has("acknowledge") else "unknown")),
        discourse="close" if has("close") else ("return" if has("return") else ("shift" if has("shift") else "continue")),
        interpersonal="listen_only" if has("listen_only") else ("advice_request" if has("advice_request") else ("acknowledge" if has("acknowledge") else ("share_difficulty" if has("difficulty") else "unknown"))),
        reference="ambiguous" if has("ambiguous_reference") else ("explicit" if has("explicit_reference") else "none"),
        cues=cues,
        legacy_rule_ids=tuple(raw_rule_ids),
        semantic_ids=tuple(semantic["semantic_ids"]),
        semantic_units=tuple(semantic["units"]),
        unmapped_semantic_labels=tuple(semantic["unmapped_labels"]),
    )
    result = asdict(frame)
    result["runtime_profile"] = runtime_identity
    result["semantic_events"] = classify_semantic_events(result["semantic_ids"])
    return result


def _recognized_labels(text: str, profile: RuntimeProfile) -> tuple[list[str], list[str]]:
    recognized = recognize_language_pack(text, profile.frame_pack)
    signal_cues, signal_rule_ids = _recognized_signal_labels(text, profile)
    return recognized["cues"] + signal_cues, recognized["legacy_rule_ids"] + signal_rule_ids


def _recognized_signal_labels(text: str, profile: RuntimeProfile) -> tuple[list[str], list[str]]:
    cues: list[str] = []
    rule_ids: list[str] = []
    for pack in profile.signal_packs:
        recognized = recognize_language_pack(text, pack)
        for cue in recognized["cues"]:
            if cue not in cues:
                cues.append(cue)
        for rule_id in recognized["legacy_rule_ids"]:
            if rule_id not in rule_ids:
                rule_ids.append(rule_id)
    return cues, rule_ids
