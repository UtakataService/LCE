"""Fail-closed Web evidence intake. It never promotes or trains automatically."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib, ipaddress, json, os, socket, tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .data_quality import DataQualityEvaluator, RawEvidence

MAX_BYTES=1_048_576
ALLOWED_CONTENT_TYPES=("text/html","text/plain","application/json","application/ld+json")
DEFAULT_ROOT=Path(".lce_data/web_intake")

class IntakeError(ValueError): pass

class _TextExtractor(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in {"script","style","noscript","svg"}: self.skip+=1
    def handle_endtag(self,tag):
        if tag in {"script","style","noscript","svg"} and self.skip:self.skip-=1
    def handle_data(self,data):
        if not self.skip and data.strip(): self.parts.append(data.strip())

@dataclass(frozen=True,slots=True)
class IntakeRecord:
    intake_id:str; source_uri:str; fetched_at:str; content_type:str; byte_length:int
    raw_hash:str; text_hash:str; title:str|None; language:str|None; license:str|None
    rights_confirmed:bool; status:str; quality_result:str; reason_codes:tuple[str,...]
    text:str

def _public_url(url:str)->None:
    parsed=urlparse(url)
    if parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password:
        raise IntakeError("PUBLIC_HTTP_URL_REQUIRED")
    if parsed.port not in {None,80,443}: raise IntakeError("NON_STANDARD_PORT_BLOCKED")
    try: infos=socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=="https" else 80),type=socket.SOCK_STREAM)
    except socket.gaierror as exc: raise IntakeError("DNS_RESOLUTION_FAILED") from exc
    for info in infos:
        ip=ipaddress.ip_address(info[4][0])
        if not ip.is_global: raise IntakeError("PRIVATE_OR_SPECIAL_ADDRESS_BLOCKED")

class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        _public_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch_url(url:str,*,timeout:float=8.0)->tuple[bytes,str,str]:
    _public_url(url)
    req=Request(url,headers={"User-Agent":"LCE-WebKnowledgeIntake/1.0 (+local research intake)"})
    with build_opener(_SafeRedirect()).open(req,timeout=timeout) as response:
        final=response.geturl(); _public_url(final)
        content_type=response.headers.get_content_type().lower()
        if content_type not in ALLOWED_CONTENT_TYPES: raise IntakeError("CONTENT_TYPE_BLOCKED")
        length=response.headers.get("Content-Length")
        if length and int(length)>MAX_BYTES: raise IntakeError("CONTENT_TOO_LARGE")
        body=response.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES: raise IntakeError("CONTENT_TOO_LARGE")
        return body,content_type,final

def extract_text(body:bytes,content_type:str)->str:
    try: decoded=body.decode("utf-8")
    except UnicodeDecodeError as exc: raise IntakeError("UTF8_REQUIRED") from exc
    if content_type=="text/html":
        parser=_TextExtractor(); parser.feed(decoded); decoded="\n".join(parser.parts)
    elif content_type in {"application/json","application/ld+json"}:
        decoded=json.dumps(json.loads(decoded),ensure_ascii=False,sort_keys=True)
    return "\n".join(line.strip() for line in decoded.splitlines() if line.strip())

def intake_url(url:str,*,language:str|None=None,license:str|None=None,rights_confirmed:bool=False,
               title:str|None=None,root:Path=DEFAULT_ROOT,body:bytes|None=None,content_type:str|None=None)->dict[str,Any]:
    if body is None: body,content_type,final=fetch_url(url)
    else: _public_url(url); final=url; content_type=(content_type or "text/plain").lower()
    if content_type not in ALLOWED_CONTENT_TYPES: raise IntakeError("CONTENT_TYPE_BLOCKED")
    if len(body)>MAX_BYTES: raise IntakeError("CONTENT_TOO_LARGE")
    text=extract_text(body,content_type)
    if len(text)<20: raise IntakeError("EXTRACTED_TEXT_TOO_SHORT")
    raw_hash="sha256:"+hashlib.sha256(body).hexdigest(); text_hash="sha256:"+hashlib.sha256(text.encode()).hexdigest()
    evidence=RawEvidence(text_hash,text,final,license,language,True if rights_confirmed else None,source_family=urlparse(final).hostname)
    report=DataQualityEvaluator().evaluate(evidence)
    status="SHADOW_CANDIDATE" if report.candidate_eligible and rights_confirmed else "QUARANTINED"
    now=datetime.now(timezone.utc).isoformat(); intake_id="web-"+raw_hash.split(":",1)[1][:20]
    record=IntakeRecord(intake_id,final,now,content_type,len(body),raw_hash,text_hash,title,language,license,rights_confirmed,
                        status,report.result.value,report.reason_codes,text)
    root=Path(root); root.mkdir(parents=True,exist_ok=True)
    target=root/(intake_id+".json")
    payload=asdict(record)
    if target.exists(): return {"ok":True,"duplicate":True,"record":json.loads(target.read_text(encoding="utf-8"))}
    fd,tmp=tempfile.mkstemp(prefix=intake_id+"-",suffix=".tmp",dir=root)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as handle: json.dump(payload,handle,ensure_ascii=False,indent=2,sort_keys=True)
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return {"ok":True,"duplicate":False,"record":payload}

def list_intakes(root:Path=DEFAULT_ROOT,limit:int=50)->list[dict[str,Any]]:
    root=Path(root)
    if not root.exists(): return []
    rows=[]
    for path in sorted(root.glob("web-*.json"),key=lambda p:p.stat().st_mtime,reverse=True)[:max(1,min(limit,200))]:
        row=json.loads(path.read_text(encoding="utf-8")); row.pop("text",None); rows.append(row)
    return rows
