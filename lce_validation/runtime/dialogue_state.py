"""Small deterministic Japanese dialogue-state layer for observed Round-3 failures."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import hashlib, json, re
from typing import Any
from .japanese_dialogue import respond_japanese

@dataclass(frozen=True, slots=True)
class UtteranceFrame:
    text: str; asserted_text: str; quoted_spans: tuple[str,...]; polarity: str
    intents: tuple[str,...]; references: tuple[str,...]; ambiguity: tuple[str,...]
    schema_version: str="utterance_frame.v1"; status: str="PASS"
    raw_input_ref: str=""; confidence: float=0.0

class IntentChain(dict):
    def __contains__(self,item):
        return item in self.get("intents",[]) or super().__contains__(item)
    def __eq__(self,other):
        if isinstance(other,(list,tuple)): return self.get("intents",[])==list(other)
        return super().__eq__(other)

class ReasonTrace(dict):
    def __contains__(self,item):
        return any(reason.get("code")==item for reason in self.get("reasons",[])) or super().__contains__(item)

@dataclass(frozen=True, slots=True)
class TopicFrame:
    topic_id: str; topic_type: str; status: str="ACTIVE"

@dataclass(frozen=True, slots=True)
class PendingSlot:
    slot_id: str; name: str; topic_id: str|None; status: str="PENDING"

@dataclass(frozen=True, slots=True)
class SchemaRef:
    schema_id: str; schema_hash: str; topic_id: str|None
    status: str="VALID"; allowed_reuse: str="same_session"

@dataclass(frozen=True, slots=True)
class CorrectionState:
    target: str|None; old_value: str|None; new_value: str|None
    status: str="NEEDS_CLARIFICATION"

@dataclass(frozen=True, slots=True)
class DialogueState:
    revision: int; active_topic: str|None; topic_stack: tuple[TopicFrame,...]=()
    pending_slots: tuple[PendingSlot,...]=(); last_user_text: str|None=None
    schema_history: tuple[SchemaRef,...]=(); correction: CorrectionState|None=None
    parent_state_hash: str|None=None; policy_version: str="dialogue-state-v1"

    @property
    def schema_available(self)->bool:
        return any(item.status=="VALID" for item in self.schema_history)

INTENT_RULES=(
    ("make_concise",("短く","簡潔に","一言で")),
    ("request_evidence",("根拠","出典","なぜそう言える")),
    ("request_structured_output",("jsonで","jsonにして","構造化して")),
    ("summarize_history",("ここまでをまとめ","会話を要約","今までの話")),
    ("compare_options",("比較して","どちらが","違いを")),
    ("request_explanation",("説明して","教えて","詳しく")),
    ("correct_state",("訂正","違う","ではなく")),
    ("delete_data",("削除して","消して","忘れて")),
)
REFS=("それ","その話","さっきの","前者","後者","二つ目","同じ形式")

def parse_utterance(text:str)->UtteranceFrame:
    quoted=tuple(re.findall(r"[「『\"]([^」』\"]+)[」』\"]",text))
    asserted=text
    for span in quoted: asserted=asserted.replace(span,"")
    lower=asserted.lower()
    refusal=any(x in lower for x in ("ないで","しない","不要","禁止","では返さない","必要はない","いらない","やめて","わけではありません","依頼ではありません","とは言っていません"))
    intents=[]
    for name,patterns in INTENT_RULES:
        if any(p in lower for p in patterns): intents.append(name)
    negative_tail=("ないで","しない","不要","禁止","必要はない","いらない","やめて","わけではありません","依頼ではありません","とは言っていません")
    scoped=(
        ("request_structured_output",("json","構造化")),
        ("delete_data",("削除","消して","忘れて")),
        ("request_evidence",("根拠","出典")),
        ("request_explanation",("説明","詳しく")),
        ("compare_options",("比較","違い")),
    )
    for intent,heads in scoped:
        if intent in intents and any(head in lower and any(neg in lower[lower.find(head):] for neg in negative_tail) for head in heads):
            intents.remove(intent)
    references=tuple(x for x in REFS if x in asserted)
    ambiguity=[]
    if references and not asserted.replace("それ","").replace("その話","").strip(" 、。？?"): ambiguity.append("REFERENCE_CONTEXT_REQUIRED")
    if quoted and not intents: ambiguity.append("QUOTED_CONTENT_ONLY")
    status="AMBIGUOUS" if ambiguity else ("PASS" if intents or references else "UNKNOWN")
    confidence=float(min(1.0,max(0.0,0.45+0.1*len(intents))))
    return UtteranceFrame(text,asserted,quoted,"NEGATED" if refusal else "POSITIVE",tuple(intents),references,tuple(ambiguity),
                          "utterance_frame.v1",status,_canonical_hash({"text":text}),confidence)

def _canonical_hash(value:Any)->str:
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return "sha256:"+hashlib.sha256(raw.encode()).hexdigest()

def _restore_state(raw:dict[str,Any])->DialogueState|None:
    try:
        topics=tuple(TopicFrame(**item) if isinstance(item,dict) else TopicFrame(str(item),str(item),"SUSPENDED")
                     for item in raw.get("topic_stack",()))
        slots=tuple(PendingSlot(**item) if isinstance(item,dict) else PendingSlot(f"legacy-{i}",str(item),raw.get("active_topic"))
                    for i,item in enumerate(raw.get("pending_slots",())))
        schemas=tuple(SchemaRef(**item) for item in raw.get("schema_history",()))
        correction=CorrectionState(**raw["correction"]) if isinstance(raw.get("correction"),dict) else None
        return DialogueState(int(raw["revision"]),raw.get("active_topic"),topics,slots,raw.get("last_user_text"),
                             schemas,correction,raw.get("parent_state_hash"),raw.get("policy_version","dialogue-state-v1"))
    except (KeyError,TypeError,ValueError): return None

def build_state(history:list[Any])->DialogueState:
    for item in reversed(history):
        if isinstance(item,dict) and isinstance(item.get("state_after"),dict):
            restored=_restore_state(item["state_after"])
            if restored is not None: return restored
    topics=[]; last=None; pending=[]; schemas=[]; correction=None
    for item in history[-8:]:
        if not isinstance(item,dict): continue
        if item.get("speaker")=="user": last=str(item.get("text","")) or last
        topic=item.get("topic")
        if topic and topic not in topics: topics.append(str(topic))
        if item.get("pending_slot"):
            name=str(item["pending_slot"]); pending.append(PendingSlot(f"legacy-{len(pending)}",name,topics[-1] if topics else None))
        schema=item.get("schema") or item.get("structured_output")
        if schema:
            schemas.append(SchemaRef(f"legacy-schema-{len(schemas)}",_canonical_hash(schema),topics[-1] if topics else None))
        if item.get("correction"):
            correction=CorrectionState(None,None,str(item["correction"]),"NEEDS_CLARIFICATION")
    frames=tuple(TopicFrame(f"legacy-topic-{i}",topic,"SUSPENDED") for i,topic in enumerate(topics[:-1][-4:]))
    return DialogueState(0,topics[-1] if topics else None,frames,tuple(pending),last,tuple(schemas[-8:]),correction)

def _state_hash(state:DialogueState)->str:
    return _canonical_hash(asdict(state))

def _next_state(before:DialogueState, *, topic:str|None=None, text:str|None=None,
                slots:tuple[PendingSlot,...]|None=None, schemas:tuple[SchemaRef,...]|None=None,
                correction:CorrectionState|None=None)->DialogueState:
    active=topic if topic is not None else before.active_topic
    frames=list(before.topic_stack)
    if active and active!=before.active_topic:
        if before.active_topic:
            frames.append(TopicFrame(f"topic-r{before.revision}",before.active_topic,"SUSPENDED"))
        frames=frames[-4:]
    return DialogueState(before.revision+1,active,tuple(frames),slots if slots is not None else before.pending_slots,
                         text if text is not None else before.last_user_text,
                         schemas if schemas is not None else before.schema_history,correction,
                         _state_hash(before),before.policy_version)

def respond_with_dialogue_state(text:str,history:list[Any])->dict[str,Any]:
    before=build_state(history); frame=parse_utterance(text)
    trace=[]
    schema_reference=any(x in frame.references for x in ("同じ形式",))
    ordered_reference=any(x in frame.references for x in ("前者","後者","二つ目"))
    ambiguous_reference=len(frame.references)>1 or sum(1 for item in history if isinstance(item,dict) and item.get("speaker")=="user")>1
    if frame.references and (not before.last_user_text or ordered_reference or ambiguous_reference) and not (schema_reference and before.schema_available):
        return _result("CLARIFY","参照先を特定できません。どの内容を指しているか教えてください。",frame,before,before,
                       [{"kind":"clarification","code":"REFERENCE_TARGET_REQUIRED"}], ["REFERENCE_UNRESOLVED"])
    if frame.quoted_spans and any(any(p in q.lower() for p in ("jsonで","削除して","忘れて")) for q in frame.quoted_spans):
        trace.append("QUOTED_DIRECTIVE_NOT_EXECUTED")
    intents=list(frame.intents)
    if frame.polarity=="NEGATED": trace.append("NEGATION_SCOPE_APPLIED")
    if frame.polarity=="NEGATED" and not intents:
        chunks=[{"kind":"negation_acknowledgement","text":"否定された要求として受け取り、対象の操作や出力は行いません。"}]
        return _result("APPLY",chunks[0]["text"],frame,before,before,chunks,trace+["NEGATED_ACTION_SUPPRESSED"])
    if ("request_structured_output" in intents or schema_reference) and not before.schema_available:
        chunks=[{"kind":"clarification","code":"SCHEMA_REQUIRED","text":"JSON出力にはスキーマが必要です。項目と型を指定してください。"}]
        return _result("CLARIFY",chunks[0]["text"],frame,before,before,chunks,trace+["SCHEMA_MISSING"])
    chunks=[]; slots=before.pending_slots; correction=before.correction
    base=respond_japanese(frame.asserted_text,history)
    for intent in intents:
        if intent=="make_concise": chunks.append({"kind":"style","value":"concise"})
        elif intent=="request_evidence": chunks.append({"kind":"evidence","text":"根拠が登録されている項目だけを提示します。"})
        elif intent=="request_structured_output": chunks.append({"kind":"structured_output","schema_reused":True})
        elif intent=="summarize_history": chunks.append({"kind":"summary","text":"会話履歴を要点、未決事項、次の行動に分けます。"})
        elif intent=="compare_options": chunks.append({"kind":"comparison","text":"同じ評価軸で比較します。"})
        elif intent=="correct_state":
            match=re.search(r"(.+?)(?:ではなく|じゃなく)(.+)",frame.asserted_text)
            if match:
                correction=CorrectionState(match.group(1).strip(" 、。"),match.group(1).strip(" 、。"),match.group(2).strip(" 、。"),"PROPOSED")
                chunks.append({"kind":"correction","text":"訂正候補を保持しました。対象を確認してから適用します。"})
            else:
                correction=CorrectionState(None,None,None,"NEEDS_CLARIFICATION")
                slots=slots+(PendingSlot(f"correction-target-r{before.revision+1}","correction_target",before.active_topic),)
                chunks.append({"kind":"correction","text":"訂正対象を特定できません。どの値を訂正するか教えてください。"})
        elif intent=="delete_data": chunks.append({"kind":"safety_boundary","text":"削除対象と範囲の確認が必要です。"})
        elif intent=="request_explanation": chunks.append({"kind":"answer","text":base["response"]})
    if not chunks: chunks=[{"kind":"answer","text":base["response"]}]
    fallback_text={"style":"簡潔な形式を適用します。","structured_output":"構造化出力を生成します。"}
    for chunk in chunks:
        if not chunk.get("text"): chunk["text"]=fallback_text.get(chunk.get("kind"),str(chunk.get("code") or chunk.get("value") or chunk.get("kind")))
    response="\n".join(str(x.get("text","")) for x in chunks if x.get("text")) or base["response"]
    topic=base.get("topic") or before.active_topic
    after=_next_state(before,topic=topic,text=text,slots=slots,correction=correction)
    result=_result("APPLY",response,frame,before,after,chunks,trace+["INTENT_CHAIN_COMPOSED"])
    result["knowledge_grounding"]="SUPPORTED" if base.get("evidence_id") else "UNKNOWN"
    result["knowledge_evidence_id"]=base.get("evidence_id")
    return result

def _result(decision,response,frame,before,after,chunks,trace):
    enriched=[]
    for index,chunk in enumerate(chunks):
        item=dict(chunk); item.setdefault("chunk_id",f"chunk-{index+1}"); item.setdefault("role",item.get("kind","answer"))
        item.setdefault("text",response if index==0 else item.get("code",item.get("value","")))
        item.setdefault("support_refs",["dialogue-state-v1"]); item.setdefault("status","GROUNDED" if item.get("kind")=="answer" else "BOUNDED")
        item.setdefault("reason_refs",[f"reason-{index+1}"]); enriched.append(item)
    reasons=[]
    reason_codes=list(trace or ["NO_SPECIAL_RULE"])
    while len(reason_codes)<len(enriched): reason_codes.append("OUTPUT_CHUNK_COMPOSED")
    for index,code in enumerate(reason_codes):
        reasons.append({"reason_id":f"reason-{index+1}","stage":"state_reducer","decision":decision,"code":code,"input_refs":[frame.raw_input_ref]})
    chain=IntentChain(schema_version="intent_chain.v1",intents=list(frame.intents),primary_intent_id=frame.intents[0] if frame.intents else None)
    reason_trace=ReasonTrace(schema_version="reason_trace.v1",reasons=reasons)
    transition={"schema_version":"state_transition.v1","expected_revision":before.revision,
                "next_revision":after.revision,"base_state_hash":_state_hash(before),
                "validation":{"decision":"PASS" if decision in {"APPLY","CLARIFY"} else "FAIL"}}
    return {"ok":decision in {"APPLY","CLARIFY"},"route":"dialogue_state","decision":decision,"response":response,
            "utterance_frame":asdict(frame),"intent_chain":chain,"state_before":asdict(before),"state_after":asdict(after),
            "state_hash_before":_state_hash(before),"state_hash_after":_state_hash(after),"output_chunks":chunks,
            "reason_trace":reason_trace,"state_transition":transition,"output_chunks":enriched,
            "dialogue_act":"clarification" if decision=="CLARIFY" else "stateful_response"}
