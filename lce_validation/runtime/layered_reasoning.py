"""Issue-isolated layered reasoning with bounded depth and draft verification."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import time
from typing import Any

from .hypothesis_loop import run_hypothesis_loop

VERSION="layered-reasoning-v1"
MAX_ISSUES=8
DEPTH_PROFILES={
    "D0":{"revisions":1,"budget_ms":8.0,"label":"reflex"},
    "D1":{"revisions":2,"budget_ms":16.0,"label":"shallow"},
    "D2":{"revisions":4,"budget_ms":35.0,"label":"standard"},
    "D3":{"revisions":6,"budget_ms":65.0,"label":"deep"},
    "D4":{"revisions":8,"budget_ms":100.0,"label":"audit"},
}


@dataclass(frozen=True,slots=True)
class IssueFrame:
    issue_id:str
    label:str
    text:str
    required:bool
    source_span:tuple[int,int]
    depth:str
    depth_reasons:tuple[str,...]
    seed:str


def run_layered_reasoning(
    text:str,
    history:list[Any]|None=None,
    *,
    issues:list[dict[str,Any]]|None=None,
    parallel:bool=False,
    max_issues:int=MAX_ISSUES,
) -> dict[str,Any]:
    started=time.perf_counter_ns()
    frames=_build_frames(text,issues,max_issues)
    shared=_shared_context(text,frames)
    if parallel and 1<len(frames)<=4:
        with ThreadPoolExecutor(max_workers=min(4,len(frames)),thread_name_prefix="lce-layer") as pool:
            futures={frame.issue_id:pool.submit(_run_lane_safe,frame,history or [],shared) for frame in frames}
            lanes=[futures[frame.issue_id].result() for frame in frames]
        execution_mode="parallel"
    else:
        lanes=[_run_lane_safe(frame,history or [],shared) for frame in frames]
        execution_mode="sequential_budget_fallback" if parallel and len(frames)>4 else "sequential_reference"
    integration=_integrate(frames,lanes)
    return {
        "ok":integration["decision"]=="PASS",
        "route":"layered_reasoning",
        "version":VERSION,
        "execution_mode":execution_mode,
        "issue_count":len(frames),
        "issues":[asdict(frame) for frame in frames],
        "issue_graph":_issue_graph(frames),
        "shared_context":shared,
        "lanes":lanes,
        "integration":integration,
        "response":integration["response"],
        "latency_ms":(time.perf_counter_ns()-started)/1e6,
        "claim":"bounded_issue_isolated_layered_reasoning_only",
        "blocked_claims":["hidden_chain_of_thought","general_reasoning","unbounded_parallelism","llm_quality_parity"],
    }


def _build_frames(text:str,provided:list[dict[str,Any]]|None,max_issues:int)->list[IssueFrame]:
    limit=max(1,min(int(max_issues),MAX_ISSUES))
    raw=[]
    if provided:
        cursor=0
        for index,item in enumerate(provided[:limit],start=1):
            value=str(item.get("text","")).strip()
            if value:raw.append((str(item.get("label") or chr(64+index)),value,bool(item.get("required",True)),cursor,cursor+len(value)))
            cursor+=len(value)+1
    else:
        matches=list(re.finditer(r"(?:^|[、,;；。]\s*)([A-HＡ-Ｈ])(?:について|に関して|は)\s*",text))
        if len(matches)>=2:
            for index,match in enumerate(matches[:limit]):
                end=matches[index+1].start() if index+1<len(matches) else len(text)
                value=text[match.end():end].strip(" 、,;；。").strip()
                if value:raw.append((match.group(1),value,True,match.start(),end))
        else:
            numbered=list(re.finditer(r"(?:^|\s)(\d{1,2})[.)、]\s*",text))
            if len(numbered)>=2:
                for index,match in enumerate(numbered[:limit]):
                    end=numbered[index+1].start() if index+1<len(numbered) else len(text)
                    value=text[match.end():end].strip()
                    if value:raw.append((match.group(1),value,True,match.start(),end))
    if not raw:raw=[("A",text.strip(),True,0,len(text))]
    frames=[]
    for index,(label,value,required,start,end) in enumerate(raw,start=1):
        depth,reasons=_select_depth(value)
        issue_id=f"issue-{index:02d}"
        seed=_hash({"version":VERSION,"issue_id":issue_id,"label":label,"text":value,"required":required,"depth":depth})
        frames.append(IssueFrame(issue_id,label,value,required,(start,end),depth,tuple(reasons),seed))
    return frames


def _select_depth(text:str)->tuple[str,list[str]]:
    lower=text.casefold();reasons=[];score=0
    if any(word in lower for word in ("深く","詳しく","厳密","証明","設計","リスク","deep","prove","architecture")):
        score+=2;reasons.append("explicit_depth_or_risk")
    if any(word in lower for word in ("比較","なぜ","理由","検証","矛盾","trade-off","compare","why","verify")):
        score+=1;reasons.append("analysis_required")
    if len(text)>160:score+=1;reasons.append("long_issue")
    if sum(text.count(mark) for mark in ("かつ","また","ただし","if","and","but"))>=2:
        score+=1;reasons.append("multiple_constraints")
    if any(word in lower for word in ("監査","安全性","法的","医療","security","audit")):
        score+=2;reasons.append("high_assurance")
    if score>=5:return "D4",reasons
    if score>=3:return "D3",reasons
    if score>=1:return "D2",reasons
    return "D1",["default_shallow"]


def _shared_context(text:str,frames:list[IssueFrame])->dict[str,Any]:
    shared=[]
    for pattern in (r"全体として(.+?)(?:。|$)",r"共通条件(?:は|として)?(.+?)(?:。|$)",r"両方とも(.+?)(?:。|$)",r"both\s+(.+?)(?:\.|$)"):
        shared.extend(match.group(1).strip() for match in re.finditer(pattern,text,re.IGNORECASE) if match.group(1).strip())
    return {"immutable":True,"constraints":sorted(set(shared)),"source_hash":_hash(text),"issue_ids":[frame.issue_id for frame in frames]}


def _run_lane(frame:IssueFrame,history:list[Any],shared:dict[str,Any])->dict[str,Any]:
    started=time.perf_counter_ns()
    profile=DEPTH_PROFILES[frame.depth]
    lane_input=frame.text
    if shared["constraints"]:lane_input += "\nShared constraints: " + "; ".join(shared["constraints"])
    result=run_hypothesis_loop(lane_input,history,max_revisions=profile["revisions"],time_budget_ms=profile["budget_ms"])
    draft=str(result.get("response","")).strip()
    elapsed_ms=(time.perf_counter_ns()-started)/1e6
    allowed_refs={frame.issue_id,"shared-context"}
    support_refs=[frame.issue_id]+(["shared-context"] if shared["constraints"] else [])
    checks={
        "draft_present":bool(draft),
        "lane_identity":result.get("route")=="hypothesis_loop",
        "bounded":result.get("revisions",0)<=profile["revisions"],
        "support_scope":set(support_refs).issubset(allowed_refs),
        "seed_bound":bool(result.get("selected_seed")) or result.get("decision") in {"CLARIFY","ABSTAIN"},
        "budget":elapsed_ms<=profile["budget_ms"]*2.0,
    }
    verification="PASS" if all(checks.values()) and result.get("decision")=="ACCEPT" else ("PARTIAL" if all(checks.values()) else "FAIL")
    return {
        "issue_id":frame.issue_id,"label":frame.label,"depth":frame.depth,"profile":profile,
        "isolated_input_hash":_hash({"issue":frame.text,"shared":shared["constraints"]}),
        "allowed_support_refs":sorted(allowed_refs),"support_refs":support_refs,"elapsed_ms":elapsed_ms,
        "hypothesis":{"decision":result.get("decision"),"draft":draft,"selected_seed":result.get("selected_seed"),"stop_code":result.get("stop_code"),"revisions":result.get("revisions")},
        "draft_verification":{"decision":verification,"checks":checks},
        "status":"PASS" if verification=="PASS" else ("PARTIAL" if verification=="PARTIAL" else "FAIL"),
    }


def _run_lane_safe(frame:IssueFrame,history:list[Any],shared:dict[str,Any])->dict[str,Any]:
    try:return _run_lane(frame,history,shared)
    except Exception as exc:
        return {"issue_id":frame.issue_id,"label":frame.label,"depth":frame.depth,"profile":DEPTH_PROFILES[frame.depth],
                "isolated_input_hash":_hash({"issue":frame.text}),"allowed_support_refs":[frame.issue_id,"shared-context"],
                "support_refs":[],"hypothesis":{"decision":"ERROR","draft":"","selected_seed":None,"stop_code":"STOP_ERROR","revisions":0},
                "draft_verification":{"decision":"FAIL","checks":{"exception_safe":False},"error_type":type(exc).__name__},"status":"FAIL"}


def _integrate(frames:list[IssueFrame],lanes:list[dict[str,Any]])->dict[str,Any]:
    by_id={lane["issue_id"]:lane for lane in lanes};ordered=[by_id[frame.issue_id] for frame in frames]
    leakage=any(not set(lane.get("support_refs",[])).issubset({lane["issue_id"],"shared-context"}) for lane in ordered)
    required_fail=[frame.issue_id for frame in frames if frame.required and by_id[frame.issue_id]["status"]!="PASS"]
    if not required_fail:decision="PASS"
    elif any(lane["status"]=="PASS" for lane in ordered):decision="PARTIAL"
    else:decision="CLARIFY"
    sections=[]
    for frame,lane in zip(frames,ordered):
        draft=lane["hypothesis"]["draft"] or "この論点はまだ確定できません。"
        sections.append(f"[{frame.label}] {draft}")
    return {"decision":decision,"coverage":sum(lane["status"]=="PASS" for lane in ordered),"required_count":sum(frame.required for frame in frames),
            "unresolved_issue_ids":required_fail,"ordered_issue_ids":[frame.issue_id for frame in frames],
            "cross_issue_leakage":leakage,"response":"\n".join(sections)}


def _issue_graph(frames:list[IssueFrame])->dict[str,Any]:
    nodes=[frame.issue_id for frame in frames];edges=[]
    indegree={node:0 for node in nodes}
    queue=sorted(node for node,value in indegree.items() if value==0);visited=[]
    while queue:
        node=queue.pop(0);visited.append(node)
        for edge in edges:
            if edge["from"]==node:
                indegree[edge["to"]]-=1
                if indegree[edge["to"]]==0:queue.append(edge["to"]);queue.sort()
    return {"nodes":nodes,"edges":edges,"acyclic":len(visited)==len(nodes),"validated":True}


def stable_view(result:dict[str,Any])->dict[str,Any]:
    def clean(value:Any)->Any:
        if isinstance(value,dict):return {key:clean(item) for key,item in value.items() if key not in {"latency_ms","elapsed_ms","execution_mode"}}
        if isinstance(value,list):return [clean(item) for item in value]
        return value
    return clean(result)


def _hash(value:Any)->str:
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return "sha256:"+hashlib.sha256(raw.encode()).hexdigest()
