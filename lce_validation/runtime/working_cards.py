"""Bounded, session-scoped cards for daily dialogue working memory."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

MAX_ACTIVE_CARDS = 12
MAX_DORMANT_CARDS = 8
MAX_PER_KIND = 3
SENSITIVE_MARKERS = ("password", "api key", "credit card", "暗証番号", "パスワード")
PROTECTED_KINDS = {"safety", "format"}
ALLOWED_KINDS = {"topic", "goal", "reference", "constraint", "tone", "depth", "safety", "format"}
MAX_VALUE_CHARS = 160


@dataclass(frozen=True, slots=True)
class WorkingCard:
    card_id: str
    kind: str
    value: str
    source: str
    language: str
    created_revision: int
    last_used_revision: int
    status: str = "ACTIVE"
    protected: bool = False


def reconcile_cards(existing: Iterable[dict[str, Any] | WorkingCard], proposed: Iterable[tuple[str, str, str]], *, revision: int, forget: bool = False) -> tuple[dict[str, Any], ...]:
    """Merge explicit cards and compact deterministically; never retain sensitive values."""
    cards = [_coerce(card) for card in existing]
    if forget:
        return ()
    for kind, value, language in proposed:
        if kind not in ALLOWED_KINDS or not value or len(value) > MAX_VALUE_CHARS or _sensitive(value):
            continue
        cards = [card for card in cards if not (card.kind == kind and card.value != value and kind in {"tone", "depth", "format"})]
        match = next((card for card in cards if card.kind == kind and card.value == value), None)
        if match:
            cards[cards.index(match)] = WorkingCard(**{**asdict(match), "last_used_revision": revision, "status": "ACTIVE"})
        else:
            cards.append(WorkingCard(_card_id(kind, value), kind, value, "user_explicit", language, revision, revision, protected=kind in PROTECTED_KINDS))
    active = [card for card in cards if card.status == "ACTIVE"]
    active = _compact(active, MAX_ACTIVE_CARDS)
    dormant = _compact([card for card in cards if card.status == "DORMANT"], MAX_DORMANT_CARDS)
    return tuple(asdict(card) for card in (*active, *dormant))


def cards_for_plan(cards: Iterable[dict[str, Any] | WorkingCard]) -> tuple[dict[str, Any], ...]:
    return tuple(asdict(card) for card in sorted((_coerce(card) for card in cards if _coerce(card).status == "ACTIVE"), key=_rank, reverse=True))


def _compact(cards: list[WorkingCard], limit: int) -> list[WorkingCard]:
    per_kind: dict[str, list[WorkingCard]] = {}
    for card in cards:
        per_kind.setdefault(card.kind, []).append(card)
    kept: list[WorkingCard] = []
    for group in per_kind.values(): kept.extend(sorted(group, key=_rank, reverse=True)[:MAX_PER_KIND])
    protected = [card for card in kept if card.protected]
    ordinary = [card for card in kept if not card.protected]
    return sorted(protected + sorted(ordinary, key=_rank, reverse=True)[:max(0, limit-len(protected))], key=lambda c: c.card_id)


def _rank(card: WorkingCard) -> tuple[int, int, int, str]:
    weight = {"safety": 100, "format": 90, "goal": 80, "topic": 70, "reference": 60, "constraint": 50, "tone": 40, "depth": 40}.get(card.kind, 10)
    return (weight, card.last_used_revision, card.created_revision, card.card_id)


def _coerce(card: dict[str, Any] | WorkingCard) -> WorkingCard:
    if isinstance(card, WorkingCard): return card
    required={"card_id","kind","value","source","language","created_revision","last_used_revision"}
    if not required <= card.keys() or card["kind"] not in ALLOWED_KINDS or len(str(card["value"])) > MAX_VALUE_CHARS or _sensitive(str(card["value"])):
        raise ValueError("INVALID_WORKING_CARD")
    return WorkingCard(**{key: card[key] for key in WorkingCard.__dataclass_fields__ if key in card})


def _card_id(kind: str, value: str) -> str:
    return "wc:sha256:" + hashlib.sha256(f"{kind}\0{value}".encode()).hexdigest()[:16]


def _sensitive(value: str) -> bool:
    text=value.casefold()
    return any(marker in text for marker in SENSITIVE_MARKERS) or bool(re.search(r"\b(?:pin|token|private key|secret)\b|[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?:\d[ -]?){12,16}", text))
