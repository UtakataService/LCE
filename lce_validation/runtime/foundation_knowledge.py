"""Data-driven, bounded foundational knowledge answers."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


FOUNDATION_DATA_PATH = Path(__file__).parents[1] / "fixtures" / "foundation_knowledge_v2.jsonl"
_REQUIRED_FIELDS = {
    "fact_id", "category", "domain", "patterns", "answer_en", "answer_ja",
    "source", "license", "status", "risk_class", "freshness_class",
    "review_status", "split",
}


@lru_cache(maxsize=4)
def load_foundation_facts(path: Path = FOUNDATION_DATA_PATH) -> tuple[dict[str, Any], ...]:
    """Load authored facts from an inspectable JSONL pack, rejecting weak records."""
    facts: list[dict[str, Any]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not _REQUIRED_FIELDS <= row.keys():
            raise ValueError(f"INVALID_FOUNDATION_FACT:{line_number}")
        if (
            not isinstance(row["fact_id"], str)
            or not isinstance(row["patterns"], list)
            or not all(isinstance(pattern, str) and pattern.strip() for pattern in row["patterns"])
            or not isinstance(row["answer_en"], str)
            or not isinstance(row["answer_ja"], str)
            or row["license"] != "CC0-1.0"
            or row["status"] != "PROMOTED"
            or row["risk_class"] != "low"
            or row["freshness_class"] != "stable"
            or row["review_status"] != "author_reviewed"
            or row["split"] not in {"train", "dev", "test"}
        ):
            raise ValueError(f"INVALID_FOUNDATION_FACT:{line_number}")
        facts.append(row)
    identifiers = [fact["fact_id"] for fact in facts]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("DUPLICATE_FOUNDATION_FACT")
    return tuple(facts)


def answer_foundation(text: str, *, data_path: Path = FOUNDATION_DATA_PATH) -> dict[str, Any] | None:
    """Return a deterministic answer only for a promoted, low-risk matching fact."""
    lowered = text.casefold()
    for fact in load_foundation_facts(Path(data_path)):
        if any(pattern.casefold() in lowered for pattern in fact["patterns"]):
            japanese = any(ord(char) > 127 for char in text)
            return {
                "fact_id": fact["fact_id"],
                "category": fact["category"],
                "domain": fact["domain"],
                "answer": fact["answer_ja"] if japanese else fact["answer_en"],
                "language": "ja" if japanese else "en",
                "source": fact["source"],
                "status": "BOUNDED",
                "risk_class": fact["risk_class"],
            }
    return None
