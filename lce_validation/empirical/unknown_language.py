from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


SCHEMA_VERSION = "unknown_language_v1"
MAX_INPUT_CHARS = 4096

_VIETNAMESE_MARKS = set("ăâđêôơưĂÂĐÊÔƠƯ")
_VIETNAMESE_TONE_MARKS = set(
    "àáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợ"
    "ùúủũụừứửữựỳýỷỹỵÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆ"
    "ÌÍỈĨỊÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ"
)
_VI_WORDS = {
    "anh", "ban", "bạn", "biet", "biết", "cam", "cảm", "chao", "chào",
    "cho", "chung", "chúng", "co", "có", "cua", "của", "duoc", "được",
    "em", "gi", "gì", "khong", "không", "la", "là", "mot", "một", "nay",
    "này", "nguoi", "người", "nhung", "những", "toi", "tôi", "va", "và",
    "xin", "yeu", "yêu",
}
_EN_WORDS = {
    "a", "am", "and", "are", "can", "do", "for", "hello", "i", "in", "is",
    "it", "know", "me", "need", "not", "of", "please", "the", "this", "to", "want",
    "what", "you", "your",
}
_AMBIGUOUS_SHORT_LATIN = {"ban", "cam", "la", "to", "no", "me"}
_TOKEN_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?|\d+(?:[.,]\d+)*|[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class ScriptProfile:
    scripts: dict[str, int]
    letters: int
    marks: int
    digits: int
    whitespace: int
    punctuation: int
    other: int
    dominant_script: str
    mixed_script: bool
    vietnamese_specific_codepoints: int
    normalization_form: str


@dataclass(frozen=True)
class LanguageHypothesis:
    language: str
    score: float
    evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...] = ()
    status: str = "open"


@dataclass
class LexicalHypothesis:
    form: str
    meaning: str
    support: int = 1
    contradiction: int = 0
    confirmed: bool = False
    examples: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        evidence = self.support + self.contradiction
        return round(self.support / evidence, 4) if evidence else 0.0


def profile_script(text: str) -> ScriptProfile:
    """Describe code points without claiming that a script identifies a language."""
    counts: dict[str, int] = {}
    letters = marks = digits = whitespace = punctuation = other = 0
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("L"):
            letters += 1
            script = _script_of(char)
            counts[script] = counts.get(script, 0) + 1
        elif category.startswith("M"):
            marks += 1
        elif category.startswith("N"):
            digits += 1
        elif char.isspace():
            whitespace += 1
        elif category.startswith("P") or category.startswith("S"):
            punctuation += 1
        else:
            other += 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    dominant = ranked[0][0] if ranked else "None"
    material = [name for name, count in ranked if count / max(letters, 1) >= 0.1]
    return ScriptProfile(
        scripts=counts,
        letters=letters,
        marks=marks,
        digits=digits,
        whitespace=whitespace,
        punctuation=punctuation,
        other=other,
        dominant_script=dominant,
        mixed_script=len(material) > 1,
        vietnamese_specific_codepoints=sum(c in _VIETNAMESE_MARKS or c in _VIETNAMESE_TONE_MARKS for c in text),
        normalization_form=_normalization_form(text),
    )


def infer_language_hypotheses(text: str, script: ScriptProfile | None = None) -> list[LanguageHypothesis]:
    """Return competing, evidence-bearing hypotheses; never equate Latin with English."""
    script = script or profile_script(text)
    words = [token.casefold() for token in _TOKEN_RE.findall(unicodedata.normalize("NFC", text)) if token[0].isalpha()]
    vi_hits = [word for word in words if word in _VI_WORDS]
    en_hits = [word for word in words if word in _EN_WORDS]
    vi_marks = script.vietnamese_specific_codepoints

    vi_score = min(0.98, 0.08 + 0.16 * len(set(vi_hits)) + 0.12 * min(vi_marks, 4))
    en_score = min(0.95, 0.08 + 0.17 * len(set(en_hits)))
    if script.dominant_script != "Latin":
        vi_score *= 0.25
        en_score *= 0.25
    if words and not vi_hits and not en_hits:
        vi_score = en_score = 0.08

    hypotheses = [
        LanguageHypothesis(
            "vi", round(vi_score, 4),
            tuple((["vietnamese_specific_diacritics"] if vi_marks else []) + [f"function_word:{w}" for w in sorted(set(vi_hits))]),
            tuple(["no_vietnamese_specific_evidence"] if not vi_marks and not vi_hits else []),
            _hypothesis_status(vi_score, en_score),
        ),
        LanguageHypothesis(
            "en", round(en_score, 4), tuple(f"function_word:{w}" for w in sorted(set(en_hits))),
            tuple(["vietnamese_specific_diacritics_present"] if vi_marks else []),
            _hypothesis_status(en_score, vi_score),
        ),
    ]
    best_known = max(vi_score, en_score)
    hypotheses.append(LanguageHypothesis(
        "unknown", round(max(0.05, 1.0 - best_known), 4),
        ("insufficient_language_evidence",) if best_known < 0.55 else ("open_set_fallback",),
        status="favored" if best_known < 0.35 else "open",
    ))
    return sorted(hypotheses, key=lambda item: (-item.score, item.language))


def segmentation_candidates(text: str) -> list[dict[str, Any]]:
    """Keep several reversible segmentations instead of asserting word boundaries."""
    nfc = unicodedata.normalize("NFC", text)
    surface = _TOKEN_RE.findall(nfc)
    candidates = [{"method": "unicode_surface", "segments": surface, "score": 0.6}]
    whitespace = [part for part in re.split(r"\s+", nfc.strip()) if part]
    if whitespace and whitespace != surface:
        candidates.append({"method": "whitespace", "segments": whitespace, "score": 0.5})
    graphemes = _grapheme_like_clusters(nfc)
    if graphemes and graphemes != surface:
        candidates.append({"method": "codepoint_clusters", "segments": graphemes, "score": 0.2})
    return candidates


class UnknownLanguageSession:
    """A reversible session overlay for first-contact language learning."""

    def __init__(self, session_id: str = "local-session", known_languages: Iterable[str] = ("en", "ja")) -> None:
        self.session_id = session_id
        self.known_languages = tuple(known_languages)
        self.encounters: list[dict[str, Any]] = []
        self.lexicon: dict[str, list[LexicalHypothesis]] = {}
        self._learning: dict[str, dict[str, Any]] = {}

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> "UnknownLanguageSession":
        session = cls(str(snapshot.get("session_id") or "local-session"))
        session.encounters = list(snapshot.get("encounters") or [])
        for key, rows in (snapshot.get("lexicon") or {}).items():
            session.lexicon[key] = [
                LexicalHypothesis(
                    form=str(row["form"]),
                    meaning=str(row["meaning"]),
                    support=int(row.get("support", 1)),
                    contradiction=int(row.get("contradiction", 0)),
                    confirmed=bool(row.get("confirmed", False)),
                    examples=list(row.get("examples") or []),
                )
                for row in rows
            ]
        session._learning = dict(snapshot.get("learning") or {})
        return session

    def encounter(self, text: str) -> dict[str, Any]:
        if not isinstance(text, str):
            raise TypeError("text must be str")
        raw = text[:MAX_INPUT_CHARS]
        script = profile_script(raw)
        record = {
            "encounter_id": _stable_id(self.session_id, str(len(self.encounters)), raw),
            "schema_version": SCHEMA_VERSION,
            "raw_form": raw,
            "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "normalized_form": unicodedata.normalize("NFC", raw),
            "raw_truncated": len(text) > MAX_INPUT_CHARS,
            "script_profile": asdict(script),
            "language_hypotheses": [asdict(item) for item in infer_language_hypotheses(raw, script)],
            "segmentations": segmentation_candidates(raw),
            "state": "SEGMENTATION_OPEN",
        }
        self.encounters.append(record)
        return record

    def teach(self, form: str, meaning: str, *, example: str = "", confirmed: bool = False) -> LexicalHypothesis:
        key = unicodedata.normalize("NFC", form).casefold().strip()
        if not key or not meaning.strip():
            raise ValueError("form and meaning must not be empty")
        alternatives = self.lexicon.setdefault(key, [])
        normalized_meaning = meaning.strip()
        for item in alternatives:
            if item.meaning.casefold() == normalized_meaning.casefold():
                item.support += 1
                item.confirmed = item.confirmed or confirmed
                if example and example not in item.examples:
                    item.examples.append(example)
                return item
        item = LexicalHypothesis(key, normalized_meaning, confirmed=confirmed, examples=[example] if example else [])
        alternatives.append(item)
        return item

    def observe(self, text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        event = self.encounter(text)
        event["context"] = dict(context or {})
        event["executable"] = False
        event["recommended_action"] = "ask_clarification" if text.strip() else "abstain"
        return event

    def apply_correction(
        self, surface: str, corrected_meaning: str, *, speaker: str, context: str
    ) -> dict[str, Any]:
        key = _surface_key(surface)
        state = self._learning.setdefault(key, _new_learning_state(surface))
        previous = state["favored_meaning"]
        status = "reopened" if previous and previous.casefold() != corrected_meaning.casefold() else "provisional"
        if status == "reopened":
            state["rejected_or_reopened_hypotheses"].append({"meaning": previous, "reason": "teacher_correction"})
        state["favored_meaning"] = corrected_meaning
        state["correction_history"].append({
            "meaning": corrected_meaning, "speaker": speaker, "context": context, "status": status,
        })
        state["speakers"].add(speaker)
        state["contexts"].add(context)
        self.teach(surface, corrected_meaning, example=context)
        return {"surface": surface, "meaning": corrected_meaning, "status": status, "scope": "session", "promoted": False}

    def add_verification(self, surface: str, meaning: str, *, speaker: str, context: str) -> dict[str, Any]:
        key = _surface_key(surface)
        state = self._learning.setdefault(key, _new_learning_state(surface))
        if state["favored_meaning"] and state["favored_meaning"].casefold() != meaning.casefold():
            state["conflicts"].add(meaning)
        else:
            state["favored_meaning"] = meaning
        state["verifications"].append({"meaning": meaning, "speaker": speaker, "context": context})
        state["speakers"].add(speaker)
        state["contexts"].add(context)
        self.teach(surface, meaning, example=context, confirmed=not state["conflicts"])
        return {"status": "verified" if not state["conflicts"] else "conflicted", "promoted": False}

    def add_counterexample(self, surface: str, *, excluded_meaning: str, context: str) -> dict[str, Any]:
        state = self._learning.setdefault(_surface_key(surface), _new_learning_state(surface))
        state["counterexamples"].append({"excluded_meaning": excluded_meaning, "context": context})
        return {"recorded": True, "promoted": False}

    def get_entry(self, surface: str) -> dict[str, Any]:
        state = self._learning.get(_surface_key(surface), _new_learning_state(surface))
        return _public_learning_state(state)

    def evaluate_promotion(self, surface: str) -> dict[str, Any]:
        state = self._learning.get(_surface_key(surface), _new_learning_state(surface))
        missing = []
        if len(state["contexts"]) < 2:
            missing.append("independent_contexts")
        if len(state["speakers"]) < 2:
            missing.append("independent_speakers")
        if not state["counterexamples"]:
            missing.append("counterexample")
        blocking = ["unresolved_conflict"] if state["conflicts"] else []
        return {"eligible": not missing and not blocking, "missing_evidence": missing, "blocking_reasons": blocking}

    def render_minimal(self, *, intent: str, language: str) -> dict[str, Any]:
        intent_meanings = {"greeting": "hello", "farewell": "goodbye", "thanks": "thank you"}
        meaning = intent_meanings.get(intent, intent)
        verified: list[str] = []
        provisional: list[str] = []
        for state in self._learning.values():
            if state["favored_meaning"].casefold() != meaning.casefold():
                continue
            has_independent_verification = bool(state["verifications"]) and len(state["speakers"]) >= 2
            has_boundary = bool(state["counterexamples"])
            if has_independent_verification and has_boundary and not state["conflicts"]:
                verified.append(state["surface"])
            else:
                provisional.append(state["surface"])
        used = sorted(verified)[:1]
        return {
            "text": " ".join(used), "mode": "broken_language", "language": language,
            "used_forms": used, "unverified_forms": provisional, "needs_confirmation": not bool(used),
        }

    def contradict(self, form: str, meaning: str) -> bool:
        key = unicodedata.normalize("NFC", form).casefold().strip()
        for item in self.lexicon.get(key, []):
            if item.meaning.casefold() == meaning.strip().casefold():
                item.contradiction += 1
                item.confirmed = False
                return True
        return False

    def confirmation_prompt(self, form: str, candidate_meaning: str) -> str:
        safe_form = form.strip()[:120]
        safe_meaning = candidate_meaning.strip()[:160]
        return f'Does "{safe_form}" mean "{safe_meaning}" here? Please answer yes/no or give a correction.'

    def broken_language(self, meanings: Iterable[str], *, unknown_marker: str = "[?]") -> dict[str, Any]:
        """Compose only confirmed forms; do not hallucinate grammar between them."""
        output: list[str] = []
        unresolved: list[str] = []
        for meaning in meanings:
            matches = [
                item for rows in self.lexicon.values() for item in rows
                if item.confirmed and item.meaning.casefold() == meaning.casefold() and item.contradiction == 0
            ]
            if matches:
                best = sorted(matches, key=lambda item: (-item.support, item.form))[0]
                output.append(best.form)
            else:
                output.append(unknown_marker)
                unresolved.append(meaning)
        return {
            "text": " ".join(output),
            "mode": "verified_chunks_only",
            "unresolved_meanings": unresolved,
            "grammar_claimed": False,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "encounters": list(self.encounters),
            "lexicon": {key: [asdict(item) | {"confidence": item.confidence} for item in rows] for key, rows in self.lexicon.items()},
            "learning": self._learning,
            "scope": "session_only",
            "formal_knowledge": False,
        }


def process_unknown_language_turn(
    text: str,
    language_hint: str = "",
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Process one reversible CLI turn and return its complete next snapshot."""
    runtime = UnknownLanguageSession.from_snapshot(session or {})
    encounter = runtime.encounter(text)
    result = analyze_encounter(text)
    return {
        "ok": True,
        "route": "known_language" if result["language"] in {"en", "ja"} else "unknown_language_learning",
        "language_hint": language_hint or None,
        "encounter": result,
        "session_state": runtime.snapshot(),
        "formal_knowledge": False,
    }


def analyze_unknown_language(text: str) -> dict[str, Any]:
    """Convenience API preserving encounter fields plus routing metadata."""
    encounter = UnknownLanguageSession().encounter(text)
    analysis = analyze_encounter(text)
    encounter.update({
        "ambiguity_flags": analysis["ambiguity_flags"],
        "code_switch_spans": analysis["code_switch_spans"],
        "meaning_verified": False,
        "executable": False,
        "primary_language": analysis["language"],
        "route": "known_language" if analysis["language"] in {"en", "ja"} else "unknown_language_learning",
    })
    return encounter


def analyze_encounter(text: str) -> dict[str, Any]:
    """Public first-contact contract used by the empirical benchmark."""
    raw = text[:MAX_INPUT_CHARS]
    normalized = unicodedata.normalize("NFC", raw)
    profile = profile_script(raw)
    hypotheses = infer_language_hypotheses(raw, profile)
    spans = _language_spans(normalized)
    span_languages = {span["language"] for span in spans}
    has_vi = any(item.language == "vi" and item.score >= 0.2 for item in hypotheses)
    has_en = any(item.language == "en" and item.score >= 0.35 for item in hypotheses)
    has_ja = profile.scripts.get("Han", 0) + profile.scripts.get("Hiragana", 0) + profile.scripts.get("Katakana", 0) > 0
    ascii_letters_only = profile.dominant_script == "Latin" and all(ord(c) < 128 for c in raw)
    ambiguity: list[str] = []
    if {"en", "vi"} <= span_languages:
        ambiguity.append("code_switch")
    if ascii_letters_only and has_vi:
        ambiguity.append("ascii_language_ambiguity")
    short_surface = normalized.casefold().strip(" .,!?:;\"'")
    short_ambiguous = short_surface in _AMBIGUOUS_SHORT_LATIN
    if short_ambiguous and "ascii_language_ambiguity" not in ambiguity:
        ambiguity.append("ascii_language_ambiguity")
    if has_ja:
        language = "ja"
    elif short_ambiguous:
        language = "unknown"
    elif has_en and not (has_vi and "ascii_language_ambiguity" in ambiguity):
        language = "en"
    elif has_vi:
        language = "vi"
    else:
        language = "unknown"
        ambiguity.append("unknown_language")
    return {
        "schema_version": SCHEMA_VERSION,
        "raw_surface": raw,
        "normalized_surface": normalized,
        "normalization": "NFC",
        "surface_hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "script_profile": asdict(profile),
        "language": language,
        "language_hypotheses": [asdict(item) for item in hypotheses],
        "code_switch_spans": spans,
        "segmentation_candidates": segmentation_candidates(raw),
        "ambiguity_flags": ambiguity,
        "status": "language_candidate" if language in {"vi", "unknown"} else "detected",
        "meaning_verified": False,
        "executable": False,
        "recommended_action": "ask_clarification" if raw.strip() else "abstain",
    }


def run_unknown_language_benchmark(cases_path: str | Any) -> dict[str, Any]:
    import json
    from pathlib import Path

    rows = [json.loads(line) for line in Path(cases_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    passed = 0
    failures: list[dict[str, Any]] = []
    normalization_ok = 0
    unsafe_execution_count = 0
    retention_ok = retention_total = 0
    for case in rows:
        result = analyze_encounter(case["input"])
        expected = case["expected"]
        checks: list[bool] = []
        checked: set[str] = set()
        candidates = {item["language"] for item in result["language_hypotheses"]}
        span_languages = {item["language"] for item in result["code_switch_spans"]}
        if "language_candidates_include" in expected:
            checks.append(set(expected["language_candidates_include"]) <= candidates)
            checked.add("language_candidates_include")
        if "span_languages_include" in expected:
            checks.append(set(expected["span_languages_include"]) <= span_languages)
            checked.add("span_languages_include")
        for key in ("language", "meaning_verified", "executable", "normalization", "normalized_surface"):
            if key in expected:
                checks.append(result[key] == expected[key])
                checked.add(key)
        if "language_not" in expected:
            checks.append(result["language"] != expected["language_not"])
            checked.add("language_not")
        if "ambiguity_flags_include" in expected:
            checks.append(set(expected["ambiguity_flags_include"]) <= set(result["ambiguity_flags"]))
            checked.add("ambiguity_flags_include")
        if "ambiguity_flags_exclude" in expected:
            checks.append(not (set(expected["ambiguity_flags_exclude"]) & set(result["ambiguity_flags"])))
            checked.add("ambiguity_flags_exclude")

        session = UnknownLanguageSession(case["case_id"])
        event = session.observe(case["input"], case.get("context"))
        lesson_result: dict[str, Any] = {}
        for lesson in case.get("teaching", []):
            for _ in range(int(lesson.get("repeat", 1))):
                if lesson.get("verification"):
                    lesson_result = session.add_verification(case["input"], lesson["meaning"], speaker=lesson["speaker"], context=lesson["context"])
                else:
                    lesson_result = session.apply_correction(case["input"], lesson["meaning"], speaker=lesson["speaker"], context=lesson["context"])
        for counterexample in case.get("counterexamples", []):
            session.add_counterexample(case["input"], excluded_meaning=counterexample["meaning"], context=counterexample["context"])
        entry = session.get_entry(case["input"])
        promotion = session.evaluate_promotion(case["input"])
        rendered = session.render_minimal(intent=expected.get("render_intent", ""), language="vi") if "render_intent" in expected else None
        values = {
            "status": lesson_result.get("status", "unobserved"),
            "favored_meaning": entry["favored_meaning"],
            "promoted": False,
            "history_preserved": len(entry["correction_history"]) >= len(case.get("teaching", [])),
            "promotion_eligible": promotion["eligible"],
            "recommended_action_in": event["recommended_action"] in expected.get("recommended_action_in", []),
            "must_not_infer_vietnamese_from_name": result["language"] != "vi",
            "must_preserve_distinct_forms": len(set(result["segmentation_candidates"][0]["segments"])) == len(result["segmentation_candidates"][0]["segments"]),
        }
        for key in ("status", "favored_meaning", "promoted", "history_preserved", "promotion_eligible", "must_not_infer_vietnamese_from_name", "must_preserve_distinct_forms"):
            if key in expected:
                checks.append(values[key] == expected[key])
                checked.add(key)
        if "recommended_action_in" in expected:
            checks.append(values["recommended_action_in"])
            checked.add("recommended_action_in")
        for expected_key, actual_key in (("missing_evidence_include", "missing_evidence"), ("blocking_reasons_include", "blocking_reasons")):
            if expected_key in expected:
                checks.append(set(expected[expected_key]) <= set(promotion[actual_key]))
                checked.add(expected_key)
        if rendered is not None:
            checked.add("render_intent")
            for key, actual in (("mode", rendered["mode"]), ("needs_confirmation", rendered["needs_confirmation"]), ("render_text", rendered["text"])):
                if key in expected:
                    checks.append(actual == expected[key])
                    checked.add(key)
            if "must_not_use_unverified_form" in expected:
                checks.append((case["input"] not in rendered["text"]) == expected["must_not_use_unverified_form"])
                checked.add("must_not_use_unverified_form")
        unchecked = set(expected) - checked
        if unchecked:
            checks.append(False)
        if result["normalization"] == "NFC":
            normalization_ok += 1
        unsafe_execution_count += int(result["executable"])
        if "english_retention" in case["phenomenon_tags"] or "japanese_retention" in case["phenomenon_tags"]:
            retention_total += 1
            retention_ok += int(all(checks))
        case_ok = all(checks)
        passed += int(case_ok)
        if not case_ok:
            failures.append({"case_id": case["case_id"], "unchecked_expected_keys": sorted(unchecked)})
    return {
        "ok": passed == len(rows), "case_count": len(rows), "passed": passed,
        "normalization_accuracy": round(normalization_ok / len(rows), 4) if rows else 1.0,
        "unsafe_execution_count": unsafe_execution_count,
        "english_japanese_retention": round(retention_ok / retention_total, 4) if retention_total else 1.0,
        "failures": failures,
    }


def _script_of(char: str) -> str:
    name = unicodedata.name(char, "")
    for script in ("LATIN", "HIRAGANA", "KATAKANA", "HANGUL", "CYRILLIC", "GREEK", "ARABIC", "HEBREW", "DEVANAGARI", "THAI"):
        if script in name:
            return script.title()
    if "CJK UNIFIED" in name or "IDEOGRAPH" in name:
        return "Han"
    return "Other"


def _normalization_form(text: str) -> str:
    for form in ("NFC", "NFD", "NFKC", "NFKD"):
        if unicodedata.is_normalized(form, text):
            return form
    return "none"


def _hypothesis_status(score: float, competitor: float) -> str:
    return "favored" if score >= 0.55 and score - competitor >= 0.2 else "open"


def _grapheme_like_clusters(text: str) -> list[str]:
    clusters: list[str] = []
    for char in text:
        if unicodedata.combining(char) and clusters:
            clusters[-1] += char
        elif not char.isspace():
            clusters.append(char)
    return clusters


def _stable_id(*parts: str) -> str:
    digest = hashlib.blake2b("\0".join(parts).encode("utf-8"), digest_size=10).hexdigest()
    return f"leu:{digest}"


def _surface_key(surface: str) -> str:
    return unicodedata.normalize("NFC", surface).casefold().strip()


def _new_learning_state(surface: str) -> dict[str, Any]:
    return {
        "surface": unicodedata.normalize("NFC", surface).strip(),
        "favored_meaning": "",
        "correction_history": [],
        "rejected_or_reopened_hypotheses": [],
        "verifications": [],
        "counterexamples": [],
        "speakers": set(),
        "contexts": set(),
        "conflicts": set(),
    }


def _public_learning_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: sorted(value) if isinstance(value, set) else list(value) if isinstance(value, list) else value
        for key, value in state.items()
    }


def _language_spans(text: str) -> list[dict[str, Any]]:
    tokens = list(re.finditer(r"[^\W\d_]+|\d+|[^\w\s]", text, re.UNICODE))
    spans: list[dict[str, Any]] = []
    for match in tokens:
        token = match.group(0)
        folded = token.casefold()
        if folded in _EN_WORDS:
            language = "en"
        elif folded in _VI_WORDS or any(c in _VIETNAMESE_MARKS or c in _VIETNAMESE_TONE_MARKS for c in token):
            language = "vi"
        elif any(_script_of(c) in {"Han", "Hiragana", "Katakana"} for c in token if c.isalpha()):
            language = "ja"
        else:
            language = "unknown"
        if spans and spans[-1]["language"] == language and spans[-1]["end"] == match.start():
            spans[-1]["text"] += token
            spans[-1]["end"] = match.end()
        else:
            spans.append({"text": token, "start": match.start(), "end": match.end(), "language": language})
    return spans
