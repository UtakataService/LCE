"""Map canonical semantic IDs to bounded policy, uptake, and interpretation signals."""
from __future__ import annotations

from typing import Any, Iterable


EVENT_IDS = {
    "privacy": "sem.policy.privacy",
    "safety": "sem.policy.safety",
    "deletion": "sem.policy.deletion",
    "output_contract": "sem.output.contract",
    "correction": "sem.uptake.correction",
    "shift": "sem.uptake.shift",
    "return": "sem.uptake.return",
    "accept": "sem.uptake.accept",
    "repeat": "sem.reference.repeat",
}


def classify_semantic_events(semantic_ids: Iterable[str]) -> dict[str, Any]:
    ids = set(semantic_ids)
    uptake = "INITIAL"
    if EVENT_IDS["correction"] in ids or "sem.discourse.repair" in ids:
        uptake = "CORRECTION"
    elif EVENT_IDS["shift"] in ids or "sem.discourse.shift" in ids:
        uptake = "SHIFT"
    elif EVENT_IDS["return"] in ids or "sem.discourse.return" in ids:
        uptake = "RETURN"
    elif EVENT_IDS["accept"] in ids or "sem.discourse.acknowledge" in ids:
        uptake = "ACCEPT"
    return {
        "privacy": EVENT_IDS["privacy"] in ids,
        "safety": EVENT_IDS["safety"] in ids,
        "deletion": EVENT_IDS["deletion"] in ids,
        "output_contract": EVENT_IDS["output_contract"] in ids,
        "interpretation": EVENT_IDS["repeat"] in ids or "sem.reference.ambiguous" in ids,
        "knowledge": "sem.speech.question" in ids,
        "uptake": uptake,
    }
