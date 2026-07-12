from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).parents[1] / "fixtures" / "japanese_dialogue_knowledge.jsonl"

def _normalize(text: str) -> str:
    return re.sub(r"[\s、。！？!?・]+", "", text).lower()

def load_japanese_dialogue_data(path: Path = DATA_PATH) -> list[dict[str, Any]]:
    rows=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        row=json.loads(line)
        row.setdefault("topic","general"); row.setdefault("intent",row["act"])
        row.setdefault("register","neutral"); row.setdefault("emotion","neutral")
        row.setdefault("negative_patterns",[]); row.setdefault("context",{})
        row.setdefault("follow_up",None); row.setdefault("confidence",0.85)
        rows.append(row)
    return rows

def _blocked(text: str, row: dict[str, Any], pattern: str) -> bool:
    normalized=_normalize(text)
    if any(_normalize(item) in normalized for item in row["negative_patterns"]): return True
    quoted=(f"「{pattern}」" in text or f"『{pattern}』" in text or f'"{pattern}"' in text) and any(x in text for x in ("とは","という言葉","と言った"))
    negated=any(_normalize(pattern+x) in normalized for x in ("じゃない","ではない","と言わないで","は不要","を禁止"))
    return quoted or negated

def _context_available(row: dict[str, Any], history: list[Any]) -> bool:
    context=row.get("context",{})
    if context.get("history_required") and not history: return False
    if context.get("schema_history_required"):
        return any(isinstance(item,dict) and (item.get("schema") or item.get("structured_output")) for item in history)
    return True

def respond_japanese(text: str, history: list[Any]) -> dict[str, Any]:
    normalized = _normalize(text)
    rows = load_japanese_dialogue_data()
    scored=[]; blocked=[]
    for row in rows:
        matched=[p for p in row["patterns"] if _normalize(p) in normalized]
        usable=[p for p in matched if not _blocked(text,row,p) and _context_available(row,history)]
        if matched and not usable: blocked.append(row["id"])
        score=max((len(_normalize(p)) for p in usable), default=0)
        scored.append((score,row,usable[0] if usable else None))
    score,row,matched_pattern=max(scored,key=lambda item:item[0])
    if score == 0:
        prior = next((str(item.get("text", "")) for item in reversed(history) if isinstance(item,dict) and item.get("speaker")=="user"), "")
        response = "まだ、その内容に確かな日本語知識を結び付けられません。言い換えるか、意味や前提をもう少し教えてください。"
        act="clarification"; evidence=None; decision="REJECT" if blocked else "UNKNOWN"
        if normalized in {"それについて", "それは", "その話"} and prior:
            response=f"直前の話題は『{prior}』です。どの点を詳しく知りたいですか。"; act="context_repair"; decision="MATCH"
    else:
        response=row["response"]; act=row["act"]; evidence=row["id"]; decision="MATCH"
    follow_up=row.get("follow_up") if score else None
    chunks=[{"kind":"answer","text":response}]
    if follow_up: chunks.append({"kind":"follow_up","code":follow_up})
    return {"ok":True,"route":"japanese_dialogue","dialogue_act":act,"response":response,
            "language_status":"ja","confidence":min(1.0,score/8) if score else 0.0,
            "evidence_id":evidence,"knowledge_rows":len(rows),"history_turn_count":len(history),
            "claim":"bounded_japanese_dialogue_only","match_decision":decision,
            "topic":row["topic"] if score else None,"intent":row["intent"] if score else act,
            "output_plan":chunks,
            "output_metadata":{"matched_pattern":matched_pattern,"blocked_candidates":blocked,"candidate_count":sum(1 for x,_,_ in scored if x>0),
                               "register":row.get("register") if score else "neutral","emotion":row.get("emotion") if score else "neutral",
                               "state_requirements":row.get("context",{}) if score else {}}}
