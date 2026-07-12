"""Wikidata CC0 general-knowledge collector and SHADOW bulk loader."""
from __future__ import annotations
from dataclasses import asdict,dataclass,replace
from datetime import datetime,timezone
import hashlib,json,os,tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from .data_quality import DataQualityEvaluator,RawEvidence

ENDPOINT="https://query.wikidata.org/sparql"
ROOT=Path(".lce_data/general_knowledge")
QUERY='''SELECT ?country ?countryLabel ?capital ?capitalLabel ?continent ?continentLabel ?currency ?currencyLabel WHERE {
  ?country wdt:P31 wd:Q3624078.
  ?country wikibase:sitelinks ?sitelinks.
  FILTER(?sitelinks >= 20)
  FILTER NOT EXISTS { ?country wdt:P576 ?dissolved. }
  OPTIONAL { ?country wdt:P36 ?capital. }
  OPTIONAL { ?country wdt:P30 ?continent. }
  OPTIONAL { ?country wdt:P38 ?currency. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ja,en". }
} LIMIT 300'''

@dataclass(frozen=True,slots=True)
class GeneralFact:
    fact_id:str; subject_id:str; subject:str; predicate:str; object_id:str|None; object:str
    language:str; source_uri:str; source_family:str; license:str; collected_at:str
    freshness_class:str; risk_class:str; quality_result:str; status:str; text:str

def fetch_country_bindings(timeout:float=30.0)->list[dict[str,Any]]:
    url=ENDPOINT+"?"+urlencode({"query":QUERY,"format":"json"})
    req=Request(url,headers={"User-Agent":"LCE-GeneralKnowledge/1.0 (local research; sequential CC0 intake)","Accept":"application/sparql-results+json"})
    with urlopen(req,timeout=timeout) as response:
        if response.headers.get_content_type() not in {"application/sparql-results+json","application/json"}: raise ValueError("UNEXPECTED_CONTENT_TYPE")
        payload=json.load(response)
    return payload["results"]["bindings"]

def _id(uri:str)->str:return uri.rsplit("/",1)[-1]
def _has_japanese(text:str)->bool:return any("ぁ"<=ch<="ん" or "ァ"<=ch<="ヶ" or "一"<=ch<="龠" for ch in text)
def _fact(subject_id,subject,predicate,object_id,obj,now):
    key=f"{subject_id}|{predicate}|{object_id or obj}"; fact_id="gk-"+hashlib.sha256(key.encode()).hexdigest()[:24]
    templates={"instance_of":"{s}は国です。","capital":"{s}の首都は{o}です。","continent":"{s}は{o}に属します。","currency":"{s}で使用される通貨には{o}があります。"}
    text=templates[predicate].format(s=subject,o=obj)
    report=DataQualityEvaluator().evaluate(RawEvidence(fact_id,text,f"https://www.wikidata.org/wiki/{subject_id}","CC0-1.0","ja",True,"wikidata-country-v1"))
    japanese_ok=_has_japanese(subject) and (predicate=="instance_of" or _has_japanese(obj))
    return GeneralFact(fact_id,subject_id,subject,predicate,object_id,obj,"ja",f"https://www.wikidata.org/wiki/{subject_id}","wikidata-country-v1","CC0-1.0",now,
                       "review-yearly" if predicate=="currency" else "stable","low",report.result.value,
                       "SHADOW" if report.candidate_eligible and japanese_ok else "QUARANTINED",text)

def transform_bindings(bindings:list[dict[str,Any]])->list[GeneralFact]:
    now=datetime.now(timezone.utc).isoformat(); facts={}
    for b in bindings:
        if not b.get("country") or not b.get("countryLabel"):continue
        sid=_id(b["country"]["value"]); subject=b["countryLabel"]["value"]
        rows=[("instance_of",None,"国")]
        for pred,key in (("capital","capital"),("continent","continent"),("currency","currency")):
            if b.get(key) and b.get(key+"Label"):rows.append((pred,_id(b[key]["value"]),b[key+"Label"]["value"]))
        for pred,oid,obj in rows:
            fact=_fact(sid,subject,pred,oid,obj,now);facts[fact.fact_id]=fact
    groups:dict[tuple[str,str],list[GeneralFact]]={}
    for fact in facts.values():
        groups.setdefault((fact.subject_id,fact.predicate),[]).append(fact)
    for group in groups.values():
        # A truthy Wikidata relation can still contain multiple historical or
        # otherwise ambiguous values. Keep those rows for audit, but never
        # expose them through SHADOW retrieval without qualifier validation.
        if len(group)>1:
            for fact in group:
                facts[fact.fact_id]=replace(fact,status="QUARANTINED")
    return sorted(facts.values(),key=lambda x:x.fact_id)

def bulk_ingest(facts:list[GeneralFact],root:Path=ROOT,*,replace_snapshot:bool=True)->dict[str,Any]:
    root=Path(root);root.mkdir(parents=True,exist_ok=True);target=root/"shadow_facts.jsonl"
    existing={}
    if target.exists() and not replace_snapshot:
        for line in target.read_text(encoding="utf-8").splitlines():
            if line.strip(): row=json.loads(line);existing[row["fact_id"]]=row
    accepted=quarantined=0
    for fact in facts:
        row=asdict(fact);existing[fact.fact_id]=row
        if fact.status=="SHADOW":accepted+=1
        else:quarantined+=1
    fd,tmp=tempfile.mkstemp(prefix="facts-",suffix=".tmp",dir=root)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as h:
            for row in sorted(existing.values(),key=lambda x:x["fact_id"]):h.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    manifest={"schema_version":"general-knowledge-corpus/v1","source":"Wikidata","license":"CC0-1.0","rows":len(existing),"accepted_this_run":accepted,"quarantined_this_run":quarantined,"generated_at":datetime.now(timezone.utc).isoformat()}
    (root/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    return manifest

def collect_and_ingest(root:Path=ROOT)->dict[str,Any]:return bulk_ingest(transform_bindings(fetch_country_bindings()),root,replace_snapshot=True)

def query_shadow(query:str,root:Path=ROOT,limit:int=10)->list[dict[str,Any]]:
    target=Path(root)/"shadow_facts.jsonl";needle=query.casefold().strip()
    if not needle or not target.exists():return []
    scored=[]
    for line in target.read_text(encoding="utf-8").splitlines():
        row=json.loads(line)
        if row.get("status")!="SHADOW":continue
        fields=(row["subject"],row["object"],row["text"],row["predicate"])
        score=sum(3 if field.casefold()==needle else 1 for field in fields if needle in field.casefold())
        if score:scored.append((score,row))
    return [row for _,row in sorted(scored,key=lambda x:(-x[0],x[1]["fact_id"]))[:max(1,min(limit,50))]]
