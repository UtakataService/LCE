"""Typed follow-up slot reducer and bounded answer planner."""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
import hashlib, json, math, re, time
from typing import Any
from .dialogue_state import respond_with_dialogue_state

@dataclass(frozen=True, slots=True)
class CompletionState:
    revision:int=0; goal:str|None=None; status:str="IDLE"
    options:tuple[str,...]=(); priority_axis:str|None=None
    deletion_target:str|None=None; deletion_scope:str|None=None
    schema_fields:tuple[str,...]=(); pending_slot:str|None=None; attempts:int=0
    slot_status:str="ABSENT"; question_revision:int|None=None
    expires_revision:int|None=None; parent_state_hash:str|None=None
    policy_version:str="dialogue-completion-v1"

AXES={"速度":"speed","速さ":"speed","精度":"accuracy","正確さ":"accuracy","費用":"cost","コスト":"cost","保守性":"maintainability","管理しやすさ":"maintainability"}
MAX_ATTEMPTS=2

def _state_hash(state:CompletionState)->str:
    raw=json.dumps(asdict(state),ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return "sha256:"+hashlib.sha256(raw.encode()).hexdigest()

def _advance(before:CompletionState, **changes)->CompletionState:
    return replace(before,revision=before.revision+1,parent_state_hash=_state_hash(before),**changes)

def _asserted_text(text:str)->tuple[str,bool]:
    quoted=re.findall(r"[「『\"]([^」』\"]+)[」』\"]",text)
    asserted=text
    for span in quoted: asserted=asserted.replace(span,"")
    return asserted,bool(quoted)

def _action_negated(text:str,heads:tuple[str,...])->bool:
    lower=text.lower()
    tails=("ないで","しない","不要","禁止","必要はない","いらない","やめて","わけではない","依頼ではない")
    return any(head in lower and any(tail in lower[lower.find(head):] for tail in tails) for head in heads)

def _restore(history:list[Any])->CompletionState:
    for item in reversed(history):
        if isinstance(item,dict) and isinstance(item.get("completion_state"),dict):
            try:
                state=CompletionState(**item["completion_state"])
                if state.revision<0 or state.attempts<0: continue
                return state
            except TypeError: pass
    return CompletionState()

def _options(text:str)->tuple[str,...]:
    parts=re.split(r"\s*(?:と|か|、|,|vs\.?|VS\.?)\s*",text.strip(" 。？?"))
    blocked={"どちらがいい","どっちがいい","比較して"}
    return tuple(x for x in parts if x and x not in blocked and 1<=len(x)<=40)[:4]

def respond_with_completion(text:str,history:list[Any])->dict[str,Any]:
    start=time.perf_counter_ns(); before=_restore(history); asserted,had_quote=_asserted_text(text); lower=asserted.lower(); trace=[]
    if before.status=="PENDING" and before.expires_revision is not None and before.revision>=before.expires_revision:
        after=_advance(before,status="EXPIRED",pending_slot=None,slot_status="EXPIRED")
        return _result("EXPIRED","確認の有効期限が切れました。必要なら最初から指定してください。",before,after,[],["QUESTION_EXPIRED"],start)
    cancel=any(re.search(pattern,lower) for pattern in (r"^(?:やっぱり)?(?:取り消し|キャンセル)(?:して)?$",r"^(?:比較|削除)(?:は|を)?やめる$"))
    if cancel and before.status=="PENDING":
        after=_advance(before,status="CANCELLED",pending_slot=None,slot_status="CANCELLED")
        return _result("CANCELLED","進行中の確認を取り消しました。",before,after,[],trace+["PENDING_CANCELLED"],start)

    if before.pending_slot=="comparison_options":
        values=_options(text)
        if len(values)<2:
            return _clarify("比較する二つの対象を「AとB」の形で教えてください。",before,"comparison_options",trace+["OPTIONS_INCOMPLETE"],start)
        after=_advance(before,goal="compare",status="PENDING",options=values,priority_axis=None,pending_slot="priority_axis",attempts=0,
                       slot_status="PENDING",question_revision=before.revision+1,expires_revision=before.revision+5)
        return _result("INCOMPLETE","比較するときに優先する基準は、速度・精度・費用・保守性のどれですか。",before,after,
                       [{"kind":"question","slot":"priority_axis"}],trace+["OPTIONS_FILLED"],start)
    if before.pending_slot=="priority_axis":
        axis=next((value for word,value in AXES.items() if word in text),None)
        if axis is None: return _clarify("速度・精度・費用・保守性から一つ選んでください。",before,"priority_axis",trace+["AXIS_INVALID"],start)
        answer=_comparison_answer(before.options,axis)
        after=_advance(before,goal="compare",status="COMPLETE",priority_axis=axis,pending_slot=None,slot_status="CONSUMED")
        return _result("COMPLETE",answer,before,after,[{"kind":"answer","target_refs":list(before.options),"axis":axis}],trace+["AXIS_FILLED","GOAL_COMPLETED"],start)
    if before.pending_slot=="deletion_target":
        target=asserted.strip(" 、。？?")
        if not target or len(target)>80:
            return _clarify("削除対象を一つ指定してください。",before,"deletion_target",trace+["TARGET_INVALID"],start)
        after=_advance(before,goal="delete",status="PENDING",deletion_target=target,pending_slot="deletion_scope",attempts=0,
                       slot_status="PENDING",question_revision=before.revision+1,expires_revision=before.revision+5)
        return _result("INCOMPLETE","削除範囲は、この会話・このセッション・すべて、のどれですか。",before,after,
                       [{"kind":"question","slot":"deletion_scope"}],trace+["TARGET_FILLED"],start)
    if before.pending_slot=="deletion_scope":
        candidates=[x for x in ("この会話","このセッション","すべて") if x in asserted]
        for candidate in tuple(candidates):
            if candidate+"ではなく" in asserted: candidates.remove(candidate)
        if len(candidates)!=1:return _clarify("削除範囲を一つだけ、この会話・このセッション・すべて、から指定してください。",before,"deletion_scope",trace+["SCOPE_AMBIGUOUS"],start)
        scope=candidates[0]
        after=_advance(before,goal="delete",status="BLOCKED",deletion_scope=scope,pending_slot=None,slot_status="VALIDATED")
        return _result("BLOCKED",f"対象『{before.deletion_target}』、範囲『{scope}』として確認しました。実削除には別の承認が必要です。",before,after,
                       [{"kind":"safety_boundary","target":before.deletion_target,"scope":scope}],trace+["SCOPE_FILLED","EXECUTION_NOT_AUTHORIZED"],start)

    if any(x in lower for x in ("どちらがいい","どっちがいい","比較して")):
        values=_options(text)
        if len(values)>=2:
            after=_advance(before,goal="compare",status="PENDING",options=values,priority_axis=None,pending_slot="priority_axis",attempts=0,
                           slot_status="PENDING",question_revision=before.revision+1,expires_revision=before.revision+5)
            prompt="比較するときに優先する基準は、速度・精度・費用・保守性のどれですか。"
            return _result("INCOMPLETE",prompt,before,after,[{"kind":"question","slot":"priority_axis"}],trace+["COMPARE_GOAL_CREATED"],start)
        after=_advance(before,goal="compare",status="PENDING",options=(),priority_axis=None,pending_slot="comparison_options",attempts=0,
                       slot_status="PENDING",question_revision=before.revision+1,expires_revision=before.revision+5)
        return _result("INCOMPLETE","比較する二つの対象を教えてください。",before,after,[{"kind":"question","slot":"comparison_options"}],trace+["COMPARE_GOAL_CREATED"],start)
    delete_requested=any(x in lower for x in ("削除して","消して")) and not _action_negated(lower,("削除","消して"))
    if delete_requested:
        target=re.sub(r"(を)?(?:削除して|消して).*$","",asserted).strip() or None
        if had_quote and not target:
            base=respond_with_dialogue_state(text,history)
            return {**base,"completion_status":"NOT_APPLICABLE","completion_state":asdict(before),"latency_ms":(time.perf_counter_ns()-start)/1e6}
        pending="deletion_scope" if target else "deletion_target"
        after=_advance(before,goal="delete",status="PENDING",deletion_target=target,deletion_scope=None,pending_slot=pending,attempts=0,
                       slot_status="PENDING",question_revision=before.revision+1,expires_revision=before.revision+5)
        prompt="削除範囲は、この会話・このセッション・すべて、のどれですか。" if target else "削除する対象を一つ指定してください。"
        return _result("INCOMPLETE",prompt,before,after,[{"kind":"question","slot":pending}],trace+["DELETE_GOAL_CREATED"],start)
    base=respond_with_dialogue_state(text,history)
    return {**base,"completion_status":"NOT_APPLICABLE","completion_state":asdict(before),"latency_ms":(time.perf_counter_ns()-start)/1e6}

def _comparison_answer(options,axis):
    labels={"speed":"速度","accuracy":"精度","cost":"費用","maintainability":"保守性"}
    return f"{options[0]}と{options[1]}を{labels[axis]}の観点で比較します。現時点の登録知識だけでは優劣を確定できないため、同じ条件で測定して判断します。"

def _clarify(text,before,slot,trace,start):
    attempts=before.attempts+1
    if attempts>=MAX_ATTEMPTS:
        after=_advance(before,status="EXPIRED",pending_slot=None,attempts=attempts,slot_status="EXPIRED")
        return _result("EXPIRED","確認回数の上限に達したため、この操作を終了しました。",before,after,[],trace+["MAX_ATTEMPTS_EXCEEDED"],start)
    after=_advance(before,status="PENDING",pending_slot=slot,attempts=attempts,slot_status="REJECTED")
    return _result("INCOMPLETE",text,before,after,[{"kind":"clarification","slot":slot}],trace,start)

def _result(status,response,before,after,chunks,trace,start):
    return {"ok":True,"route":"dialogue_completion","completion_status":status,"response":response,
            "completion_state":asdict(after),"state_before":asdict(before),"output_chunks":chunks,
            "state_hash_before":_state_hash(before),"state_hash_after":_state_hash(after),
            "state_transition":{"expected_revision":before.revision,"next_revision":after.revision,
                                "base_state_hash":_state_hash(before),"parent_hash_valid":after.parent_state_hash==_state_hash(before)},
            "reason_trace":trace,"latency_ms":float((time.perf_counter_ns()-start)/1e6)}
