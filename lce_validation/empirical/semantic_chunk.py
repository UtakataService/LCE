from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .nl_normalization import normalize_tokens
from .seeded_dialogue import stable_seed


SCHEMA_VERSION = "semantic_chunk_v1"
MAX_INPUT_CHARS = 4096
MAX_CHUNKS = 16
MAX_ENTITIES = 12
MAX_CONSTRAINTS = 12
MAX_REFERENCES = 8

INTENT_PATTERNS = [
    ("request_explanation", ("explain", "describe", "how does", "what is")),
    ("request_implementation", ("implement", "build", "create", "write code", "add support")),
    ("request_modification", ("change", "modify", "update", "improve", "refactor")),
    ("continue_task", ("continue", "proceed", "next step", "keep going")),
    ("request_comparison", ("compare", "difference", "versus", " vs ")),
    ("request_verification", ("verify", "validate", "test", "prove", "check")),
    ("request_information", ("show", "list", "find", "tell me")),
]

PREDICATE_ALIASES = {
    "implement": ("implement", "build", "create", "write"),
    "modify": ("change", "modify", "update", "improve", "refactor"),
    "continue": ("continue", "proceed", "keep going"),
    "explain": ("explain", "describe", "what is", "how does"),
    "compare": ("compare", "difference", "versus"),
    "verify": ("verify", "validate", "test", "prove", "check"),
    "delete": ("delete", "remove"),
    "send": ("send", "publish", "post"),
}

MODALITY_PATTERNS = {
    "required": ("must", "have to", "required to", "need to"),
    "prohibited": ("must not", "do not", "don't", "never", "without changing"),
    "preferred": ("should", "prefer", "ideally"),
    "permitted": ("may", "can", "allowed to"),
}

REFERENCE_PATTERNS = {
    "previous_turn": ("previous", "earlier", "before", "last turn", "above"),
    "deictic_this": ("this", "these"),
    "deictic_that": ("that", "those"),
    "anaphoric_it": (" it ", " its ", "same one", "same approach"),
}

STOP_ENTITIES = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "i", "in", "is", "it", "me", "of", "on", "or", "please", "that", "the",
    "these", "this", "those", "to", "we", "what", "with", "without", "you",
    "must", "should", "never", "not", "can", "may",
}


@dataclass(frozen=True)
class SemanticChunk:
    chunk_id: str
    text: str
    seed: int
    language: str
    intent: str
    predicate: str
    entities: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    requested_outcome: str = ""
    polarity: str = "positive"
    modality: str = "asserted"
    ambiguity_flags: list[str] = field(default_factory=list)
    confidence: float = 0.0
    semantic_signature: str = ""
    signature_features: list[str] = field(default_factory=list)


def parse_semantic_chunks(text: str, *, language_hint: str = "auto") -> dict[str, Any]:
    normalized = _normalize_input(text)
    parts = _split_chunks(normalized)
    chunks = [_parse_chunk(part, index, language_hint) for index, part in enumerate(parts, start=1)]
    return {
        "ok": bool(chunks),
        "schema_version": SCHEMA_VERSION,
        "input": text,
        "normalized_input": normalized,
        "chunks": [asdict(chunk) for chunk in chunks],
        "chunk_count": len(chunks),
        "limits": {
            "max_input_chars": MAX_INPUT_CHARS,
            "max_chunks": MAX_CHUNKS,
            "truncated": len(text) > MAX_INPUT_CHARS or len(_raw_parts(normalized)) > MAX_CHUNKS,
        },
        "claim": "bounded_english_first_semantic_chunk_parser_only",
        "blocked_claims": [
            "general_language_understanding",
            "learned_semantic_embedding",
            "cross_lingual_semantic_equivalence",
            "open_domain_coreference_resolution",
            "llm_quality_parity",
        ],
    }


def semantic_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_features = set(left.get("signature_features", []))
    right_features = set(right.get("signature_features", []))
    if not left_features and not right_features:
        return 1.0
    union = left_features | right_features
    return round(len(left_features & right_features) / len(union), 6) if union else 0.0


def run_semantic_chunk_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case in load_jsonl(cases_path):
        result = parse_semantic_chunks(case["input"], language_hint=case.get("language_hint", "auto"))
        repeat = parse_semantic_chunks(case["input"], language_hint=case.get("language_hint", "auto"))
        chunk = result["chunks"][case.get("chunk_index", 0)]
        checks = {
            "intent": chunk["intent"] == case["expected_intent"],
            "predicate": chunk["predicate"] == case["expected_predicate"],
            "references": set(case.get("expected_references", [])) <= set(chunk["references"]),
            "constraints": all(value in " ".join(chunk["constraints"]) for value in case.get("constraint_contains", [])),
            "ambiguity": set(case.get("expected_ambiguity", [])) <= set(chunk["ambiguity_flags"]),
            "deterministic": result == repeat,
        }
        rows.append({
            "case_id": case["case_id"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "checks": checks,
            "case_ok": all(checks.values()),
            "result": result,
        })
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "determinism_accuracy": _ratio(row["checks"]["deterministic"] for row in rows),
        "by_tag": _by_tag(rows),
        "claim": "bounded_english_first_semantic_chunk_parser_only",
        "blocked_claims": ["general_language_understanding", "llm_quality_parity"],
    }
    _write_jsonl(out / "semantic_chunk_rows.jsonl", rows)
    (out / "semantic_chunk_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _parse_chunk(text: str, index: int, language_hint: str) -> SemanticChunk:
    lowered = f" {text.lower()} "
    tokens = normalize_tokens(text)
    intent = _first_match(lowered, INTENT_PATTERNS, "state_information")
    predicate = _predicate(lowered)
    modality = _modality(lowered)
    if modality in {"required", "prohibited"} and re.match(r"\s*(?:the|a|an)\s+", lowered):
        intent = "state_information"
    polarity = "negative" if modality == "prohibited" or re.search(r"\b(?:not|no|never)\b", lowered) else "positive"
    constraints = _constraints(text, lowered)
    references = _references(lowered)
    entities = _entities(text, tokens, predicate)
    requested_outcome = _requested_outcome(intent, predicate, entities)
    ambiguity = _ambiguity_flags(text, references, entities, intent)
    language = _language(text, language_hint)
    features = _signature_features(intent, predicate, entities, constraints, references, polarity, modality, language)
    signature = hashlib.blake2b("\0".join(features).encode("utf-8"), digest_size=12).hexdigest()
    confidence = _confidence(intent, predicate, ambiguity, language)
    return SemanticChunk(
        chunk_id=f"sem-{index:02d}", text=text,
        seed=stable_seed(text, salt="lce-semantic-chunk-v1"), language=language,
        intent=intent, predicate=predicate, entities=entities[:MAX_ENTITIES],
        constraints=constraints[:MAX_CONSTRAINTS], references=references[:MAX_REFERENCES],
        requested_outcome=requested_outcome, polarity=polarity, modality=modality,
        ambiguity_flags=ambiguity, confidence=confidence,
        semantic_signature=signature, signature_features=features,
    )


def _normalize_input(text: str) -> str:
    return re.sub(r"\s+", " ", text[:MAX_INPUT_CHARS].strip())


def _raw_parts(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?;])\s+|\n+", text) if part.strip()]


def _split_chunks(text: str) -> list[str]:
    return _raw_parts(text)[:MAX_CHUNKS]


def _first_match(text: str, rows: list[tuple[str, tuple[str, ...]]], default: str) -> str:
    for label, patterns in rows:
        if any(pattern in text for pattern in patterns):
            return label
    return default


def _predicate(text: str) -> str:
    for predicate, aliases in PREDICATE_ALIASES.items():
        if any(re.search(rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])", text) for alias in aliases):
            return predicate
    return "state"


def _modality(text: str) -> str:
    for label in ("prohibited", "required", "preferred", "permitted"):
        if any(pattern in text for pattern in MODALITY_PATTERNS[label]):
            return label
    return "asserted"


def _constraints(original: str, lowered: str) -> list[str]:
    markers = ("must", "must not", "do not", "don't", "without", "only", "keep", "remain", "should", "never")
    if not any(marker in lowered for marker in markers):
        return []
    clauses = re.split(r"[,;]|(?:and|but)", original, flags=re.IGNORECASE)
    return [clause.strip(" .") for clause in clauses if any(marker in clause.lower() for marker in markers)]


def _references(text: str) -> list[str]:
    found = [label for label, patterns in REFERENCE_PATTERNS.items() if any(pattern in text for pattern in patterns)]
    if re.search(r"\b(?:it|its)\b", text) and "anaphoric_it" not in found:
        found.append("anaphoric_it")
    return found


def _entities(original: str, tokens: list[str], predicate: str) -> list[str]:
    quoted = [a or b for a, b in re.findall(r'"([^"\n]+)"|\'([^\'\n]+)\'', original)]
    candidates = quoted + [token for token in tokens if len(token) > 2 and token not in STOP_ENTITIES]
    aliases = {item for values in PREDICATE_ALIASES.values() for item in values}
    entities: list[str] = []
    for item in candidates:
        normalized = item.lower().strip()
        if normalized == predicate or normalized in aliases or normalized in entities:
            continue
        entities.append(normalized)
    return entities


def _requested_outcome(intent: str, predicate: str, entities: list[str]) -> str:
    if not intent.startswith("request_") and intent != "continue_task":
        return ""
    target = entities[0] if entities else "unspecified_target"
    return f"{predicate}:{target}"


def _ambiguity_flags(text: str, references: list[str], entities: list[str], intent: str) -> list[str]:
    flags = []
    if references and not entities:
        flags.append("unresolved_reference")
    if len(text.split()) <= 2 and intent == "state_information":
        flags.append("underspecified_intent")
    if intent.startswith("request_") and not entities:
        flags.append("missing_target")
    return flags


def _language(text: str, hint: str) -> str:
    if hint in {"en", "ja", "mixed"}:
        return hint
    has_ja = bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text))
    has_en = bool(re.search(r"[A-Za-z]", text))
    return "mixed" if has_ja and has_en else "ja" if has_ja else "en"


def _signature_features(intent: str, predicate: str, entities: list[str], constraints: list[str], references: list[str], polarity: str, modality: str, language: str) -> list[str]:
    features = [f"intent:{intent}", f"predicate:{predicate}", f"polarity:{polarity}", f"modality:{modality}", f"language:{language}"]
    features += [f"entity:{item}" for item in sorted(set(entities))]
    features += [f"constraint:{' '.join(normalize_tokens(item))}" for item in sorted(set(constraints))]
    features += [f"reference:{item}" for item in sorted(set(references))]
    return sorted(features)


def _confidence(intent: str, predicate: str, ambiguity: list[str], language: str) -> float:
    score = 0.92
    if intent == "state_information":
        score -= 0.16
    if predicate == "state":
        score -= 0.12
    score -= 0.15 * len(ambiguity)
    if language != "en":
        score -= 0.2
    return round(max(0.05, min(0.99, score)), 3)


def _ratio(values: Any) -> float:
    rows = list(values)
    return round(sum(1 for value in rows if value) / len(rows), 6) if rows else 0.0


def _by_tag(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        for tag in row["phenomenon_tags"]:
            entry = result.setdefault(tag, {"case_count": 0, "case_ok": 0})
            entry["case_count"] += 1
            entry["case_ok"] += int(row["case_ok"])
    for entry in result.values():
        entry["accuracy"] = round(entry["case_ok"] / entry["case_count"], 6)
    return result


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
