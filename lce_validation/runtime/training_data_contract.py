"""Data and tokenizer contracts for reproducible scaling pilots.

The contract does not store training text.  It stores enough provenance to
reject an unsafe or leaky corpus before a tokenizer or model run consumes it.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class TrainingDataContractError(ValueError):
    pass


ALLOWED_SPLITS = {"train", "validation", "interaction_blind", "sealed", "quarantine"}
ALLOWED_LANGUAGES = {"en", "ja", "multilingual"}


@dataclass(frozen=True, slots=True)
class CorpusManifest:
    manifest_id: str
    manifest_version: str
    sources: tuple[dict[str, Any], ...]
    tokenizer: dict[str, Any]
    snapshot_hash: str

    def language_mix(self, *, split: str = "train") -> dict[str, float]:
        counts: dict[str, int] = {}
        total = 0
        for source in self.sources:
            if source["split"] != split:
                continue
            total += source["document_count"]
            counts[source["language"]] = counts.get(source["language"], 0) + source["document_count"]
        return {language: count / total for language, count in sorted(counts.items())} if total else {}


def load_corpus_manifest(path: str | Path) -> CorpusManifest:
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrainingDataContractError("UNREADABLE_CORPUS_MANIFEST") from exc
    return validate_corpus_manifest(raw)


def validate_corpus_manifest(raw: Mapping[str, Any]) -> CorpusManifest:
    required = {"schema_version", "manifest_id", "manifest_version", "sources", "tokenizer"}
    if not isinstance(raw, Mapping) or raw.get("schema_version") != "lce-training-corpus/v1":
        raise TrainingDataContractError("INVALID_CORPUS_MANIFEST_SCHEMA")
    if required - set(raw) or not isinstance(raw["manifest_id"], str) or not isinstance(raw["manifest_version"], str):
        raise TrainingDataContractError("INVALID_CORPUS_MANIFEST_IDENTITY")
    sources = _validate_sources(raw["sources"])
    tokenizer = _validate_tokenizer(raw["tokenizer"])
    _validate_split_isolation(sources)
    snapshot_hash = "sha256:" + hashlib.sha256(_canonical_json(dict(raw)).encode("utf-8")).hexdigest()
    return CorpusManifest(raw["manifest_id"], raw["manifest_version"], sources, tokenizer, snapshot_hash)


def _validate_sources(value: Any) -> tuple[dict[str, Any], ...]:
    required = {
        "source_id", "source_family", "license", "consent_basis", "language", "split",
        "document_count", "raw_snapshot_hash", "normalized_snapshot_hash", "dedup_policy_id",
        "pii_policy_id", "quality_policy_id",
    }
    if not isinstance(value, list) or not value:
        raise TrainingDataContractError("INVALID_CORPUS_SOURCES")
    source_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for source in value:
        if not isinstance(source, Mapping) or required - set(source):
            raise TrainingDataContractError("INVALID_CORPUS_SOURCE")
        if source["source_id"] in source_ids or source["language"] not in ALLOWED_LANGUAGES or source["split"] not in ALLOWED_SPLITS:
            raise TrainingDataContractError("INVALID_CORPUS_SOURCE_ENUM")
        if not isinstance(source["document_count"], int) or source["document_count"] <= 0:
            raise TrainingDataContractError("INVALID_CORPUS_DOCUMENT_COUNT")
        if source["split"] != "quarantine" and (not source["license"] or not source["consent_basis"]):
            raise TrainingDataContractError("UNLICENSED_OR_UNGOVERNED_SOURCE")
        source_ids.add(source["source_id"])
        normalized.append(dict(source))
    if not {"en", "ja"}.issubset({source["language"] for source in normalized if source["split"] == "train"}):
        raise TrainingDataContractError("MISSING_EN_JA_TRAINING_COVERAGE")
    return tuple(normalized)


def _validate_tokenizer(value: Any) -> dict[str, Any]:
    required = {"tokenizer_id", "algorithm", "vocabulary_size", "normalization_id", "byte_fallback", "training_snapshot_hash"}
    if not isinstance(value, Mapping) or required - set(value):
        raise TrainingDataContractError("INVALID_TOKENIZER_CONTRACT")
    if value["algorithm"] not in {"bpe", "unigram"} or not isinstance(value["vocabulary_size"], int) or value["vocabulary_size"] < 1024:
        raise TrainingDataContractError("INVALID_TOKENIZER_CONFIGURATION")
    if value["byte_fallback"] is not True:
        raise TrainingDataContractError("TOKENIZER_REQUIRES_BYTE_FALLBACK")
    return dict(value)


def _validate_split_isolation(sources: tuple[dict[str, Any], ...]) -> None:
    families: dict[str, set[str]] = {}
    for source in sources:
        families.setdefault(source["source_family"], set()).add(source["split"])
    for splits in families.values():
        if "train" in splits and ("interaction_blind" in splits or "sealed" in splits):
            raise TrainingDataContractError("CROSS_SPLIT_SOURCE_FAMILY")


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
