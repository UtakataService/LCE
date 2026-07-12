"""Attribution-preserving Wikipedia introduction collector for LCE SHADOW."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from .data_quality import DataQualityEvaluator, RawEvidence

ROOT=Path(".lce_data/wikipedia_general_education")
LICENSE="CC-BY-SA-4.0"
LICENSE_URL="https://creativecommons.org/licenses/by-sa/4.0/"
MAX_EXCERPT_CHARS=1400
API_TEMPLATE="https://{language}.wikipedia.org/w/api.php"
SUMMARY_TEMPLATE="https://{language}.wikipedia.org/api/rest_v1/page/summary/{title}"
ALLOWED_CATEGORIES=frozenset({"science","culture","daily_life","technology"})
CATEGORY_RISK={"science":"low","culture":"low","daily_life":"contextual","technology":"contextual"}
HIGH_RISK_TERMS=("medical advice","medical treatment","legal advice","financial advice","investment advice","how to commit suicide","self-harm instruction","weapon construction")

# Low-risk, durable topics. High-stakes and fast-moving domains deliberately stay out.
SEEDS: tuple[tuple[str,str],...] = (
    ("Earth","science"),("Moon","science"),("Sun","science"),("Solar System","science"),("Water","science"),
    ("Weather","science"),("Plant","science"),("Animal","science"),("Ocean","science"),("Forest","science"),
    ("Mathematics","science"),("Physics","science"),("Chemistry","science"),("Astronomy","science"),("Geography","science"),
    ("Music","culture"),("Painting","culture"),("Literature","culture"),("Film","culture"),("Theatre","culture"),
    ("Food","daily_life"),("Cooking","daily_life"),("Coffee","daily_life"),("Tea","daily_life"),("Bread","daily_life"),
    ("Fruit","daily_life"),("Bicycle","daily_life"),("House","daily_life"),("City","daily_life"),("School","daily_life"),
    ("Library","daily_life"),("Calendar","daily_life"),("Time","daily_life"),("Computer","technology"),("Internet","technology"),
    ("Telephone","technology"),("Photography","technology"),("Map","daily_life"),("Language","culture"),("Communication","daily_life"),
)


@dataclass(frozen=True, slots=True)
class WikipediaKnowledgeRecord:
    record_id:str
    title:str
    category:str
    language:str
    canonical_url:str
    revision_id:int | None
    revision_at:str | None
    fetched_at:str
    license:str
    license_url:str
    attribution:str
    source_family:str
    revision_url:str | None
    modified:bool
    excerpt:str
    excerpt_hash:str
    risk_class:str
    quality_result:str
    status:str


def fetch_intro(title:str,*,language:str="en",timeout:float=15.0,max_attempts:int=2)->dict[str,Any]:
    if language not in {"en","ja"}: raise ValueError("SUPPORTED_WIKIPEDIA_LANGUAGE_REQUIRED")
    params={"action":"query","format":"json","formatversion":"2","prop":"extracts|revisions|info",
            "exintro":"1","explaintext":"1","redirects":"1","rvprop":"ids|timestamp","inprop":"url","maxlag":"5","titles":title}
    url=API_TEMPLATE.format(language=language)+"?"+urlencode(params)
    request=Request(url,headers={"User-Agent":"LCE-WikipediaGeneralEducation/1.0 (local research corpus; contact: local-admin)","Accept":"application/json"})
    payload=None
    for attempt in range(max(1,min(max_attempts,3))):
        try:
            with urlopen(request,timeout=timeout) as response:
                if response.headers.get_content_type() not in {"application/json","text/json"}: raise ValueError("WIKIPEDIA_UNEXPECTED_CONTENT_TYPE")
                payload=json.load(response)
            break
        except HTTPError as exc:
            if exc.code not in {429,503} or attempt+1>=max_attempts: raise ValueError(f"WIKIPEDIA_HTTP_{exc.code}") from exc
            retry_after=exc.headers.get("Retry-After","")
            try: wait_seconds=float(retry_after)
            except ValueError: wait_seconds=15.0
            time.sleep(max(1.0,min(wait_seconds,60.0)))
        except URLError as exc:
            if attempt+1>=max_attempts: raise ValueError("WIKIPEDIA_NETWORK_ERROR") from exc
            time.sleep(5.0)
    if payload is None: raise ValueError("WIKIPEDIA_NO_RESPONSE")
    pages=payload.get("query",{}).get("pages",[])
    if len(pages)!=1 or pages[0].get("missing") or not pages[0].get("extract"): raise ValueError("WIKIPEDIA_PAGE_UNAVAILABLE")
    return pages[0]


def fetch_summary_intro(title:str,*,language:str="en",timeout:float=15.0,max_attempts:int=2)->dict[str,Any]:
    if language not in {"en","ja"}: raise ValueError("SUPPORTED_WIKIPEDIA_LANGUAGE_REQUIRED")
    url=SUMMARY_TEMPLATE.format(language=language,title=quote(title.replace(" ","_"),safe=""))
    request=Request(url,headers={"User-Agent":"LCE-WikipediaGeneralEducation/1.0 (local research corpus; contact: local-admin)","Accept":"application/json"})
    payload=None
    for attempt in range(max(1,min(max_attempts,3))):
        try:
            with urlopen(request,timeout=timeout) as response:
                if response.headers.get_content_type() not in {"application/json","text/json"}: raise ValueError("WIKIPEDIA_UNEXPECTED_CONTENT_TYPE")
                payload=json.load(response)
            break
        except HTTPError as exc:
            if exc.code not in {429,503} or attempt+1>=max_attempts: raise ValueError(f"WIKIPEDIA_HTTP_{exc.code}") from exc
            try: wait_seconds=float(exc.headers.get("Retry-After","15"))
            except ValueError: wait_seconds=15.0
            time.sleep(max(1.0,min(wait_seconds,60.0)))
        except URLError as exc:
            if attempt+1>=max_attempts: raise ValueError("WIKIPEDIA_NETWORK_ERROR") from exc
            time.sleep(5.0)
    if not payload or not payload.get("extract"): raise ValueError("WIKIPEDIA_PAGE_UNAVAILABLE")
    canonical=str(payload.get("content_urls",{}).get("desktop",{}).get("page") or f"https://{language}.wikipedia.org/wiki/{quote(title.replace(' ','_'))}")
    return {"title":payload["title"],"extract":payload["extract"],"fullurl":canonical,
            "revisions":[{"revid":payload.get("revision"),"timestamp":payload.get("timestamp")}]}


def make_record(page:dict[str,Any],category:str,*,language:str="en",now:str|None=None)->WikipediaKnowledgeRecord:
    title=str(page["title"]); full_excerpt=" ".join(str(page["extract"]).split()); excerpt=full_excerpt[:MAX_EXCERPT_CHARS].strip()
    url=str(page.get("fullurl") or f"https://{language}.wikipedia.org/wiki/{quote(title.replace(' ','_'))}")
    revision=(page.get("revisions") or [{}])[0]
    raw_revision_id=revision.get("revid")
    try: revision_id=int(raw_revision_id) if raw_revision_id is not None else None
    except (TypeError,ValueError): revision_id=None
    revision_at=revision.get("timestamp")
    digest="sha256:"+hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    key=f"{language}|{title}|{revision_id or digest}"; record_id="wp-"+hashlib.sha256(key.encode()).hexdigest()[:24]
    report=DataQualityEvaluator().evaluate(RawEvidence(record_id,excerpt,url,LICENSE,language,True,"wikipedia-general-education-v1"))
    status="SHADOW" if report.candidate_eligible else "QUARANTINED"
    fetched_at=now or datetime.now(timezone.utc).isoformat()
    revision_url=f"{url}?oldid={revision_id}" if revision_id is not None else None
    candidate=WikipediaKnowledgeRecord(record_id,title,category,language,url,revision_id,revision_at,fetched_at,LICENSE,LICENSE_URL,
                                       f"Wikipedia contributors, '{title}', {url}, {LICENSE}","wikipedia-general-education-v1",revision_url,
                                       len(full_excerpt)>len(excerpt),excerpt,digest,"low",report.result.value,status)
    return _normalize_record(candidate)


def collect_records(*,language:str="en",seeds:tuple[tuple[str,str],...]=SEEDS,delay_seconds:float=1.5)->list[WikipediaKnowledgeRecord]:
    records=[]
    for index,(title,category) in enumerate(seeds):
        page=fetch_summary_intro(title,language=language)
        records.append(make_record(page,category,language=language))
        if delay_seconds>0 and index+1<len(seeds): time.sleep(delay_seconds)
    return records


def bulk_ingest(records:list[WikipediaKnowledgeRecord],root:Path=ROOT)->dict[str,Any]:
    root=Path(root); root.mkdir(parents=True,exist_ok=True); target=root/"shadow_records.jsonl"
    rows={record.record_id:asdict(_normalize_record(record)) for record in records}
    fd,tmp=tempfile.mkstemp(prefix="wikipedia-",suffix=".tmp",dir=root)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as handle:
            for row in sorted(rows.values(),key=lambda item:item["record_id"]): handle.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    accepted=sum(row["status"]=="SHADOW" for row in rows.values())
    manifest={"schema_version":"wikipedia-general-education/v1","source":"Wikipedia","license":LICENSE,
              "rows":len(rows),"shadow":accepted,"quarantined":len(rows)-accepted,"categories":_counts(rows,"category"),
              "languages":_counts(rows,"language"),"risks":_counts(rows,"risk_class"),"readiness":"SHADOW_DEMO_UNVERIFIED",
              "generated_at":datetime.now(timezone.utc).isoformat()}
    (root/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    return manifest


def query_shadow(query:str,root:Path=ROOT,limit:int=10)->list[dict[str,Any]]:
    target=Path(root)/"shadow_records.jsonl"; needle=query.casefold().strip()
    if not needle or not target.exists(): return []
    scored=[]
    for line in target.read_text(encoding="utf-8").splitlines():
        row=json.loads(line)
        if row.get("status")!="SHADOW": continue
        fields=(row["title"],row["category"],row["excerpt"])
        score=sum(3 if field.casefold()==needle else 1 for field in fields if needle in field.casefold())
        if score: scored.append((score,row))
    return [row for _,row in sorted(scored,key=lambda item:(-item[0],item[1]["record_id"]))[:max(1,min(limit,50))]]


def public_metadata(rows:list[dict[str,Any]])->list[dict[str,Any]]:
    fields=("record_id","title","category","language","canonical_url","revision_id","revision_at","revision_url","fetched_at",
            "license","license_url","attribution","source_family","modified","risk_class","quality_result","status")
    return [{key:row.get(key) for key in fields} for row in rows]


def collect_and_ingest(root:Path=ROOT,*,language:str="en")->dict[str,Any]:
    return bulk_ingest(collect_records(language=language),root)


def _counts(rows:dict[str,dict[str,Any]],key:str)->dict[str,int]:
    result:dict[str,int]={}
    for row in rows.values(): result[row[key]]=result.get(row[key],0)+1
    return dict(sorted(result.items()))


def _normalize_record(record:WikipediaKnowledgeRecord)->WikipediaKnowledgeRecord:
    excerpt=" ".join(record.excerpt.split())[:MAX_EXCERPT_CHARS]
    lowered=(record.title+" "+excerpt).casefold()
    url_ok=record.canonical_url.startswith(f"https://{record.language}.wikipedia.org/wiki/")
    valid=(record.language in {"en","ja"} and record.category in ALLOWED_CATEGORIES and record.license==LICENSE and
           record.license_url==LICENSE_URL and record.source_family=="wikipedia-general-education-v1" and
           record.revision_id is not None and bool(record.revision_at) and url_ok and bool(record.attribution) and
           not any(term in lowered for term in HIGH_RISK_TERMS))
    risk=CATEGORY_RISK.get(record.category,"restricted") if valid else "restricted"
    report=DataQualityEvaluator().evaluate(RawEvidence(record.record_id,excerpt,record.canonical_url,record.license,record.language,True,record.source_family))
    status="SHADOW" if valid and report.candidate_eligible else "QUARANTINED"
    revision_url=f"{record.canonical_url}?oldid={record.revision_id}" if record.revision_id is not None else None
    digest="sha256:"+hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    return replace(record,excerpt=excerpt,excerpt_hash=digest,revision_url=revision_url,risk_class=risk,
                   quality_result=report.result.value,status=status,modified=bool(record.modified or excerpt!=record.excerpt))
