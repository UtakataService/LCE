"""Deterministic Hypothesis -> Verify -> Revise loop for bounded LCE tasks."""
from __future__ import annotations
from dataclasses import asdict,dataclass
import hashlib,json,math,time
from typing import Any
from .dialogue_completion import respond_with_completion
from .structured_io import run_structured_io

@dataclass(frozen=True,slots=True)
class Hypothesis:
    hypothesis_id:str; revision:int; seed:str; parent_revision_hash:str|None; domain:str
    response:str; payload:dict[str,Any]; repairs:tuple[str,...]; score:float; verdict:str
    revision_hash:str=""; verification_hash:str=""

def _seed(original:str,revision:int,repairs,checks)->str:
    raw=json.dumps([original,revision,repairs,checks],ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return "sha256:"+hashlib.sha256(raw.encode()).hexdigest()

def _hash(value:Any)->str:
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return "sha256:"+hashlib.sha256(raw.encode()).hexdigest()

def _domain(text,schema,history):
    lower=text.lower()
    structured_cue=any(x in lower for x in ("返して","出力","形式","構造化","スキーマ","項目"))
    if schema is not None or "構造化" in lower or ("json" in lower and structured_cue):return "structured"
    if any(x in lower for x in ("比較","どちら","どっち","違い")):return "comparison"
    if any(x in lower for x in ("根拠","出典","なぜ")) and not any(x in lower for x in ("根拠は不要","根拠不要","出典は不要","根拠はいらない")):return "evidence"
    for item in reversed(history):
        if not isinstance(item,dict): continue
        state=item.get("completion_state") or {}
        if state.get("goal")=="compare" or state.get("pending_slot") in {"comparison_options","priority_axis"}: return "comparison"
        if item.get("domain") in {"comparison","evidence","structured"}: return item["domain"]
        if item.get("schema") or item.get("structured_output"): return "structured"
    return "dialogue"

def run_hypothesis_loop(text:str,history:list[Any],*,data:Any=None,schema:Any=None,max_revisions:int=6,time_budget_ms:float=50.0)->dict[str,Any]:
    started=time.perf_counter_ns(); domain=_domain(text,schema,history); trace=[]; seen=set(); parent=None; repairs=[]; selected=None
    try: requested_revisions=int(max_revisions)
    except (TypeError,ValueError): requested_revisions=1
    revision_limit=max(1,min(requested_revisions,12))
    budget=float(time_budget_ms) if isinstance(time_budget_ms,(int,float)) and not isinstance(time_budget_ms,bool) else 0.0
    if not math.isfinite(budget) or budget<=0:
        return _stopped(domain,"STOP_BUDGET","時間予算が無効または消費済みです。",trace,started)
    input_snapshot_hash=_hash({"text":text,"history":history,"data":data,"schema":schema,"policy":"hvr-v1"})
    original=_seed(input_snapshot_hash,0,[],{"policy_version":"hvr-v1"})
    for revision in range(revision_limit):
        if (time.perf_counter_ns()-started)/1e6>=budget: trace.append({"revision":revision,"stop":"STOP_BUDGET"}); break
        if domain=="structured": result=run_structured_io(instruction=text,data=data,schema=schema)
        else: result=respond_with_completion(text,history)
        verifier_results={
            "syntax":{"decision":"PASS"},
            "policy":{"decision":"PASS" if not _policy_violation(text,result) else "FAIL"},
            "evidence":{"decision":"PASS"},
            "coherence":{"decision":"PASS" if bool(result.get("response")) else "FAIL"},
            "complete":{"decision":"PASS"},
        }
        new_repairs=[]
        if domain=="structured" and not result.get("ok"):
            verifier_results["syntax"]={"decision":"FAIL","code":"STRUCTURED_OUTPUT_INVALID"}; new_repairs.append("REQUEST_VALID_SCHEMA_OR_DATA")
        if domain=="evidence" and not result.get("evidence_id"):
            verifier_results["evidence"]={"decision":"UNKNOWN","code":"EVIDENCE_UNAVAILABLE"}; new_repairs.append("MARK_EVIDENCE_UNAVAILABLE")
        if domain=="comparison" and result.get("completion_status") in {"INCOMPLETE","NOT_APPLICABLE"}:
            verifier_results["complete"]={"decision":"UNKNOWN","code":"COMPARISON_SLOT_MISSING"}; new_repairs.append("ASK_FOR_COMPARISON_SLOT")
        options=result.get("completion_state",{}).get("options",())
        if domain=="comparison" and len(options)>2:
            verifier_results["complete"]={"decision":"FAIL","code":"COMPARISON_TARGET_COUNT_INVALID"}; new_repairs.append("REQUEST_EXACTLY_TWO_TARGETS")
        axis_words=("速度","精度","費用","コスト","保守性")
        if domain=="comparison" and sum(word in text for word in axis_words)>1:
            verifier_results["complete"]={"decision":"UNKNOWN","code":"MULTIPLE_AXES_AMBIGUOUS"}; new_repairs.append("ASK_FOR_ONE_AXIS")
        frame=result.get("utterance_frame",{})
        if domain=="dialogue" and frame.get("status") in {"UNKNOWN","AMBIGUOUS"}:
            verifier_results["complete"]={"decision":"UNKNOWN","code":"DIALOGUE_INTENT_UNRESOLVED"}; new_repairs.append("ASK_FOR_INTENT_CLARIFICATION")
        if domain=="dialogue" and result.get("knowledge_grounding")=="UNKNOWN" and "request_explanation" in frame.get("intents",()):
            verifier_results["evidence"]={"decision":"UNKNOWN","code":"KNOWLEDGE_GROUNDING_UNAVAILABLE"}; new_repairs.append("MARK_KNOWLEDGE_UNKNOWN")
        aggregate=_aggregate(verifier_results)
        score=sum(1.0 for value in verifier_results.values() if value["decision"]=="PASS")/len(verifier_results)
        seed=_seed(original,revision,repairs+new_repairs,verifier_results)
        state=(seed,json.dumps(result.get("completion_state",{}),sort_keys=True,ensure_ascii=False))
        verdict="ACCEPT" if aggregate=="PASS" else ("REVISE" if aggregate in {"FAIL","UNKNOWN"} else "REJECT")
        response=str(result.get("response", ""))
        if domain=="structured" and not response:
            response="構造化出力には有効なスキーマと入力データが必要です。"
        if "MARK_EVIDENCE_UNAVAILABLE" in new_repairs: response="確認できる根拠が不足しているため、現時点では確かな回答を出せません。"
        verification_hash=_hash(verifier_results)
        revision_hash=_hash({"input":input_snapshot_hash,"revision":revision,"seed":seed,"parent":parent,"response":response,
                             "payload_hash":_hash(result),"repairs":repairs+new_repairs,"verification":verification_hash})
        hyp=Hypothesis(f"hyp-{revision+1}",revision,seed,parent,domain,response,result,tuple(repairs+new_repairs),score,verdict,revision_hash,verification_hash)
        trace.append({"hypothesis":asdict(hyp),"verifiers":verifier_results,"aggregate":aggregate})
        selected=hyp
        if verdict=="ACCEPT":break
        fingerprint=_hash({"aggregate":aggregate,"repairs":new_repairs,"verifiers":verifier_results})
        if state in seen or fingerprint in seen: trace.append({"revision":revision,"stop":"STOP_REPEATED_FAILURE"});break
        seen.add(state); seen.add(fingerprint); parent=revision_hash; repairs.extend(new_repairs)
        if new_repairs and revision>0: trace.append({"revision":revision,"stop":"STOP_NO_FURTHER_IMPROVEMENT"});break
    if selected is None:return _stopped(domain,"STOP_BUDGET","検証予算内に仮説を作成できませんでした。",trace,started)
    final="ACCEPT" if selected.verdict=="ACCEPT" else ("CLARIFY" if any("ASK_" in x or "REQUEST_" in x for x in selected.repairs) else "ABSTAIN")
    stop_code={"ACCEPT":"STOP_PASS","CLARIFY":"STOP_CLARIFY","ABSTAIN":"STOP_ABSTAIN"}[final]
    return {"ok":final=="ACCEPT","route":"hypothesis_loop","domain":domain,"decision":final,"response":selected.response,
            "selected_hypothesis_id":selected.hypothesis_id,"selected_seed":selected.seed,"selected_revision_hash":selected.revision_hash,
            "stop_code":stop_code,"input_snapshot_hash":input_snapshot_hash,"revisions":len([x for x in trace if "hypothesis" in x]),
            "trace":trace,"latency_ms":float((time.perf_counter_ns()-started)/1e6),"claim":"bounded_hypothesis_verification_only"}

def _aggregate(results:dict[str,dict[str,Any]])->str:
    decisions=[item.get("decision","ERROR") for item in results.values()]
    if "FAIL" in decisions:return "FAIL"
    if "ERROR" in decisions:return "ERROR"
    if "STALE" in decisions:return "STALE"
    if "UNKNOWN" in decisions:return "UNKNOWN"
    return "PASS" if decisions and all(item=="PASS" for item in decisions) else "ERROR"

def _policy_violation(text:str,result:dict[str,Any])->bool:
    lower=text.lower()
    denied=any(x in lower for x in ("削除しないで","実行しないで","jsonでは返さない"))
    executed=result.get("completion_status") in {"COMPLETE"} and result.get("completion_state",{}).get("goal")=="delete"
    return bool(denied and executed)

def _stopped(domain:str,code:str,response:str,trace:list[dict[str,Any]],started:int)->dict[str,Any]:
    decision="CLARIFY" if code=="STOP_BUDGET" else "ABSTAIN"
    return {"ok":False,"route":"hypothesis_loop","domain":domain,"decision":decision,"response":response,
            "selected_hypothesis_id":None,"selected_seed":None,"selected_revision_hash":None,"stop_code":code,
            "revisions":0,"trace":trace,"latency_ms":float((time.perf_counter_ns()-started)/1e6),
            "claim":"bounded_hypothesis_verification_only"}
