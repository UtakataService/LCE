"""Bounded interpretation, uptake, and repair vertical slice for daily dialogue."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class Interpretation:
    interpretation_id: str
    dimension: Literal["content","interpersonal","permission","discourse"]
    hypothesis: str
    confidence: float
    status: Literal["TENTATIVE","CONFIRMED","RETRACTED"]="TENTATIVE"


def run_interpretation_slice(text: str, history: list[Any] | None = None) -> dict[str, Any]:
    history=list(history or [])[-8:]
    before=_restore(history)
    proposed=_propose(text)
    uptake=_classify_uptake(text,before)
    updated=_update(before,proposed,uptake)
    step=_response_step(updated,uptake)
    return {"ok":True,"mode":"bounded_interpretation_slice","response":step["text"],"response_steps":[step],"uptake":uptake,
            "interpretation_set":[asdict(item) for item in updated],"interpretation_state":{"items":[asdict(item) for item in updated],"hash":_hash(updated)},
            "claim":"bounded_tentative_interpretation_only","blocked_claims":["mind_reading","persistent_personality","general_dialogue_understanding"]}


def _propose(text: str) -> list[Interpretation]:
    lowered=text.casefold(); rows=[]
    def add(dimension: str,hypothesis: str,confidence: float) -> None:
        key=f"{dimension}|{hypothesis}"; rows.append(Interpretation("ih:"+hashlib.sha256(key.encode()).hexdigest()[:12],dimension,hypothesis,confidence))
    if any(token in lowered for token in ("tired","stressed","rough day","疲れ","しんど","困っ")): add("content","reports_difficulty",0.6)
    if any(token in lowered for token in ("listen","hear me out","聞いてほしい","愚痴")): add("permission","requests_listening",0.9)
    if any(token in lowered for token in ("advice","what should","どうすれば","意見が")): add("permission","advice_scope_unclear",0.5)
    if any(token in lowered for token in ("actually","i meant","訂正","そういう意味じゃない")): add("discourse","corrects_prior_interpretation",0.9)
    if any(token in lowered for token in ("by the way","another topic","ところで","別の話")): add("discourse","shifts_topic",0.8)
    if not rows: add("content","meaning_unclear",0.2)
    return rows


def _classify_uptake(text: str, before: list[Interpretation]) -> str:
    lowered=text.casefold()
    if not before:return "INITIAL"
    if any(token in lowered for token in ("actually","no,","not that","違う","訂正")):return "CORRECTION"
    if any(token in lowered for token in ("yes","yeah","exactly","そう","うん")):return "ACCEPTANCE"
    if any(token in lowered for token in ("by the way","another topic","ところで","別の話")):return "SHIFT"
    return "UNRESOLVED"


def _update(before: list[Interpretation], proposed: list[Interpretation], uptake: str) -> list[Interpretation]:
    prior=[item for item in before if not (uptake=="CORRECTION" and item.status=="TENTATIVE")]
    if uptake=="ACCEPTANCE": prior=[Interpretation(**{**asdict(item),"status":"CONFIRMED"}) for item in prior]
    return (prior+proposed)[-6:]


def _response_step(items: list[Interpretation], uptake: str) -> dict[str,str]:
    labels={item.hypothesis for item in items if item.status!="RETRACTED"}
    if "requests_listening" in labels:return {"kind":"reflect","text":"I hear that you want to be heard. I will stay with what you are saying before offering solutions."}
    if "reports_difficulty" in labels:return {"kind":"reflect_and_choice","text":"That sounds difficult. Would it help to talk through it, or would you rather I simply listen?"}
    if "corrects_prior_interpretation" in labels:return {"kind":"repair","text":"Thanks for correcting me. I will treat the earlier interpretation as tentative rather than settled."}
    if "shifts_topic" in labels:return {"kind":"transition","text":"Okay, we can shift topics. What would you like to focus on now?"}
    return {"kind":"clarify","text":"I may be missing the point. Could you say a little more about what you want from this turn?"}


def _restore(history: list[Any]) -> list[Interpretation]:
    for item in reversed(history):
        raw=item.get("interpretation_state") if isinstance(item,dict) else None
        if isinstance(raw,dict) and isinstance(raw.get("items"),list):
            try:return [Interpretation(**row) for row in raw["items"]]
            except (TypeError,ValueError):return []
    return []


def _hash(items: list[Interpretation]) -> str:
    return "sha256:"+hashlib.sha256(json.dumps([asdict(item) for item in items],sort_keys=True,separators=(",",":")).encode()).hexdigest()
