"""State-aware, margin-gated resolver over UtteranceFrame features."""
from __future__ import annotations

from typing import Any

MARGIN=2

def resolve_frame(frame: dict[str, Any], state: Any) -> dict[str, Any]:
    scores: dict[str,int]={}
    def add(act: str, value: int) -> None: scores[act]=scores.get(act,0)+value
    if frame["discourse"]=="close": add("close",6)
    if frame["discourse"]=="return": add("topic_return",5 if getattr(state,"topic_stack",()) else 2)
    if frame["discourse"]=="shift": add("topic_shift",4)
    if frame["polarity"]=="repair": add("self_correction",5)
    if frame["interpersonal"]=="listen_only": add("listen_only",5)
    if frame["interpersonal"]=="advice_request": add("consented_advice",3)
    if frame["interpersonal"]=="acknowledge": add("backchannel",3)
    if frame["interpersonal"]=="share_difficulty": add("share_difficulty",3)
    if frame["reference"]=="ambiguous":
        add("reference_resolution" if getattr(state,"references",()) else "reference_clarification",4)
    if frame["sentence_type"]=="question": add("question",2)
    ranked=sorted(scores.items(),key=lambda item:(-item[1],item[0]))
    if not ranked: return {"decision":"CLARIFY","reason":"NO_FRAME_CANDIDATE","candidates":[]}
    act,score=ranked[0]; second=ranked[1][1] if len(ranked)>1 else 0
    if score<3 or score-second<MARGIN: return {"decision":"CLARIFY","reason":"LOW_MARGIN","candidates":ranked}
    return {"decision":"SELECT","act":act,"score":score,"margin":score-second,"candidates":ranked}
