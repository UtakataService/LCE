from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from .knowledge_unit import Status


class KnowledgeUnitNotFoundError(KeyError): pass
class KnowledgeUnitConflictError(RuntimeError): pass
class KnowledgeUnitValidationError(ValueError): pass
class PromotionRejected(KnowledgeUnitValidationError): pass
class RepositoryUnavailable(RuntimeError): pass


_TRANSITIONS = {
    "OBSERVED": {"QUARANTINED"}, "QUARANTINED": {"NORMALIZED", "REJECTED"},
    "NORMALIZED": {"LINKED", "REJECTED"}, "LINKED": {"VERIFIED", "DISPUTED", "REJECTED"},
    "VERIFIED": {"SHADOW", "DISPUTED", "REJECTED"},
    "SHADOW": {"ACTIVE_L1", "DISPUTED", "EXPIRED", "RETRACTED"},
    "ACTIVE_L1": {"DISPUTED", "SUPERSEDED", "RETRACTED", "EXPIRED"},
    "DISPUTED": {"VERIFIED", "REJECTED"},
}
_RETRYABLE = {1205, 1213}
_REQUIRED_CHECKS = {"provenance", "license", "privacy", "contradiction", "regression"}


def _id(value: str) -> bytes: return uuid.UUID(str(value)).bytes
def _text(value: Any) -> str: return str(uuid.UUID(bytes=bytes(value)))
def _now() -> datetime: return datetime.now(timezone.utc).replace(tzinfo=None)
def _json(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _command_hash(value: Any) -> bytes: return hashlib.sha256(_json(value).encode("utf-8")).digest()


class MySQLKnowledgeUnitRepository:
    """Tenant-isolated MySQL 8/MariaDB 10.6 Knowledge Unit repository.

    Connections must expose a DictCursor-compatible cursor. No operation falls
    back to JSON or another tenant when the database is unavailable.
    """

    def __init__(self, connection_factory: Callable[[], Any], tenant_id: str, *, max_retries: int = 3) -> None:
        if not tenant_id or not tenant_id.strip():
            raise KnowledgeUnitValidationError("tenant_id is required")
        self.connection_factory, self.tenant_id = connection_factory, tenant_id.strip()
        self.max_retries = max(0, max_retries)

    def create_observation(self, draft: dict[str, Any], *, actor: Any, idempotency_key: str) -> dict[str, Any]:
        self._validate_draft(draft)
        logical_id, revision_id = str(draft.get("logical_id") or uuid.uuid4()), str(uuid.uuid4())
        command = {"op": "create", "draft": draft, "actor": actor}
        def work(c):
            replay = self._begin_idempotency(c, idempotency_key, command)
            if replay: return replay
            now = _now()
            c.execute("INSERT INTO knowledge_heads(tenant_id,logical_id,status,current_revision_no,lock_version,created_at,updated_at) VALUES(%s,%s,'OBSERVED',0,0,%s,%s)", (self.tenant_id,_id(logical_id),now,now))
            self._insert_revision(c, logical_id, revision_id, 1, "OBSERVED", draft, actor, now)
            c.execute("UPDATE knowledge_heads SET current_revision_id=%s,current_revision_no=1,lock_version=1 WHERE tenant_id=%s AND logical_id=%s", (_id(revision_id),self.tenant_id,_id(logical_id)))
            self._event_outbox(c, logical_id, revision_id, 1, None, "OBSERVED", actor, idempotency_key, now)
            self._finish_idempotency(c, idempotency_key, logical_id, revision_id)
            return {"logical_id": logical_id}
        result = self._transaction(work)
        return self.get_current(result["logical_id"])

    def get_current(self, logical_id: str) -> dict[str, Any]:
        return self._read_one("WHERE h.tenant_id=%s AND h.logical_id=%s AND r.revision_id=h.current_revision_id", (self.tenant_id,_id(logical_id)))

    def get_revision(self, revision_id: str) -> dict[str, Any]:
        return self._read_one("WHERE r.tenant_id=%s AND r.revision_id=%s", (self.tenant_id,_id(revision_id)))

    def list_history(self, logical_id: str) -> list[dict[str, Any]]:
        conn = self.connection_factory()
        try:
            with conn.cursor() as c:
                c.execute(self._select()+" WHERE r.tenant_id=%s AND r.logical_id=%s ORDER BY r.revision_no", (self.tenant_id,_id(logical_id)))
                return [self._decode(x) for x in c.fetchall()]
        finally: conn.close()

    def revise(self, logical_id: str, patch: dict[str, Any], reason: str, actor: Any, expected_revision_no: int, idempotency_key: str) -> dict[str, Any]:
        return self._append(logical_id, patch, None, None, actor, reason, expected_revision_no, idempotency_key)

    def put_evidence(self, evidence: Any, *, actor: Any, idempotency_key: str) -> dict[str, Any]:
        row = dict(evidence) if isinstance(evidence, dict) else {
            name: getattr(evidence, name) for name in
            ("evidence_id", "raw_text", "normalized_text", "source_uri", "content_hash", "license", "language")
        }
        command = {"op": "put_evidence", "evidence": row, "actor": actor}
        def work(c):
            replay = self._begin_idempotency(c, idempotency_key, command)
            if replay:
                return row
            try: evidence_id = _id(row["evidence_id"])
            except ValueError: evidence_id = uuid.uuid5(uuid.NAMESPACE_URL, self.tenant_id + ":" + row["evidence_id"]).bytes
            digest = bytes.fromhex(row["content_hash"])
            c.execute("INSERT INTO evidence_items(tenant_id,evidence_id,raw_text,normalized_text,source_uri,content_hash,license_code,language_tag,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (self.tenant_id,evidence_id,row["raw_text"],row["normalized_text"],row["source_uri"],digest,row["license"],row["language"],_now()))
            self._finish_idempotency(c,idempotency_key,str(uuid.UUID(bytes=evidence_id)),str(uuid.UUID(bytes=evidence_id)))
            return row
        return self._transaction(work)

    def attach_evidence(self, logical_id: str, link: Any, actor: Any, expected_revision_no: int, idempotency_key: str) -> dict[str, Any]:
        row = dict(link) if isinstance(link, dict) else {name: getattr(link,name) for name in ("evidence_id","stance","source_ref")}
        try: evidence_id = _id(row["evidence_id"])
        except ValueError: evidence_id = uuid.uuid5(uuid.NAMESPACE_URL, self.tenant_id + ":" + row["evidence_id"]).bytes
        command={"op":"attach_evidence","logical_id":logical_id,"link":row,"expected":expected_revision_no}
        def work(c):
            replay=self._begin_idempotency(c,idempotency_key,command)
            if replay: return replay
            c.execute("SELECT evidence_id FROM evidence_items WHERE tenant_id=%s AND evidence_id=%s",(self.tenant_id,evidence_id))
            if not c.fetchone(): raise KnowledgeUnitNotFoundError(row["evidence_id"])
            c.execute(self._select()+" WHERE h.tenant_id=%s AND h.logical_id=%s AND r.revision_id=h.current_revision_id FOR UPDATE",(self.tenant_id,_id(logical_id)))
            current_row=c.fetchone()
            if not current_row: raise KnowledgeUnitNotFoundError(logical_id)
            current=self._decode(current_row)
            if current["revision_no"] != expected_revision_no: raise KnowledgeUnitConflictError("stale expected revision")
            no,rid,now=expected_revision_no+1,str(uuid.uuid4()),_now()
            self._insert_revision(c,logical_id,rid,no,current["status"],current,actor,now)
            c.execute("INSERT INTO evidence_links(tenant_id,revision_id,evidence_id,stance,source_ref,linked_by,linked_at) SELECT tenant_id,%s,evidence_id,stance,source_ref,linked_by,linked_at FROM evidence_links WHERE tenant_id=%s AND revision_id=%s",(_id(rid),self.tenant_id,_id(current["revision_id"])))
            c.execute("INSERT INTO evidence_links(tenant_id,revision_id,evidence_id,stance,source_ref,linked_by,linked_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",(self.tenant_id,_id(rid),evidence_id,row["stance"],row["source_ref"],str(actor),now))
            c.execute("UPDATE knowledge_heads SET current_revision_id=%s,current_revision_no=%s,lock_version=lock_version+1,updated_at=%s WHERE tenant_id=%s AND logical_id=%s AND current_revision_no=%s",(_id(rid),no,now,self.tenant_id,_id(logical_id),expected_revision_no))
            if c.rowcount != 1: raise KnowledgeUnitConflictError("concurrent head update")
            self._event_outbox(c,logical_id,rid,no,current["status"],current["status"],actor,idempotency_key,now)
            self._finish_idempotency(c,idempotency_key,logical_id,rid)
            return {"logical_id":logical_id}
        result=self._transaction(work)
        return self.get_current(result["logical_id"])

    def transition(self, logical_id: str, target_status: str, *, decision: dict[str, Any], expected_revision_no: int, idempotency_key: str) -> dict[str, Any]:
        if getattr(target_status, "value", target_status) == Status.ACTIVE_L1.value:
            raise PromotionRejected("ACTIVE_L1 requires the dedicated promote API")
        actor = decision.get("actor", "system")
        return self._append(logical_id, {}, target_status, decision, actor, "transition", expected_revision_no, idempotency_key)

    def promote(self, logical_id: str, *, decision: dict[str, Any], actor: Any,
                expected_revision_no: int, idempotency_key: str) -> dict[str, Any]:
        if actor is None or not str(actor).strip():
            raise PromotionRejected("promotion actor is required")
        if not isinstance(decision, dict):
            raise PromotionRejected("promotion decision must be a mapping")
        decision_actor = decision.get("actor")
        if decision_actor is not None and str(decision_actor) != str(actor):
            raise PromotionRejected("promotion actor differs from decision actor")
        signed_decision = dict(decision)
        signed_decision["actor"] = actor
        return self._append(logical_id, {}, Status.ACTIVE_L1.value, signed_decision,
                            actor, "promote_active_l1", expected_revision_no,
                            idempotency_key, allow_promotion=True)

    def retract(self, logical_id: str, reason: str, actor: Any, expected_revision_no: int, idempotency_key: str) -> dict[str, Any]:
        return self._append(logical_id, {}, "RETRACTED", None, actor, reason, expected_revision_no, idempotency_key)

    def _append(self, logical_id, patch, target, decision, actor, reason, expected, key,
                *, allow_promotion=False):
        command={"op":"append","logical_id":logical_id,"patch":patch,"target":target,
                 "decision":decision,"actor":actor,"reason":reason,"expected":expected}
        def work(c):
            replay=self._begin_idempotency(c,key,command)
            if replay: return replay
            c.execute(self._select()+" WHERE h.tenant_id=%s AND h.logical_id=%s AND r.revision_id=h.current_revision_id FOR UPDATE",(self.tenant_id,_id(logical_id)))
            row=c.fetchone()
            if not row: raise KnowledgeUnitNotFoundError(logical_id)
            current=self._decode(row)
            if current["revision_no"] != expected: raise KnowledgeUnitConflictError("stale expected revision")
            status=target or current["status"]
            if target:
                if target not in _TRANSITIONS.get(current["status"],set()): raise PromotionRejected(f"invalid transition {current['status']} -> {target}")
                if target == Status.ACTIVE_L1.value:
                    if not allow_promotion:
                        raise PromotionRejected("ACTIVE_L1 requires the dedicated promote API")
                    c.execute("SELECT COUNT(*) AS n FROM evidence_links WHERE tenant_id=%s AND revision_id=%s AND stance='supports'", (self.tenant_id, _id(current["revision_id"])))
                    evidence_row = c.fetchone()
                    current["supporting_evidence_count"] = int((evidence_row.get("n") if isinstance(evidence_row, dict) else evidence_row[0]) or 0)
                    self._validate_promotion(current, decision or {})
            draft={**current,**patch}; self._validate_draft(draft)
            no, rid, now=expected+1,str(uuid.uuid4()),_now()
            self._insert_revision(c,logical_id,rid,no,status,draft,actor,now)
            c.execute("INSERT INTO evidence_links(tenant_id,revision_id,evidence_id,stance,source_ref,linked_by,linked_at) SELECT tenant_id,%s,evidence_id,stance,source_ref,linked_by,linked_at FROM evidence_links WHERE tenant_id=%s AND revision_id=%s",(_id(rid),self.tenant_id,_id(current["revision_id"])))
            c.execute("UPDATE knowledge_heads SET current_revision_id=%s,current_revision_no=%s,status=%s,lock_version=lock_version+1,updated_at=%s WHERE tenant_id=%s AND logical_id=%s AND current_revision_no=%s",(_id(rid),no,status,now,self.tenant_id,_id(logical_id),expected))
            if c.rowcount != 1: raise KnowledgeUnitConflictError("concurrent head update")
            self._event_outbox(c,logical_id,rid,no,current["status"],status,actor,key,now)
            self._finish_idempotency(c,key,logical_id,rid)
            return {"logical_id":logical_id}
        result=self._transaction(work)
        return self.get_current(result["logical_id"])

    def _validate_promotion(self, current, decision):
        checks=decision.get("checks",{})
        missing=sorted(k for k in _REQUIRED_CHECKS if checks.get(k) is not True)
        if missing: raise PromotionRejected("ACTIVE_L1 checks must PASS: "+", ".join(missing))
        if not current.get("scope") or current.get("language",{}).get("identification_state") != "verified":
            raise PromotionRejected("ACTIVE_L1 requires defined scope and verified language")
        if int(current.get("supporting_evidence_count", 0)) < 1:
            raise PromotionRejected("ACTIVE_L1 requires supporting evidence")
        if not decision.get("actor") or not decision.get("policy_version"):
            raise PromotionRejected("ACTIVE_L1 requires actor and policy_version")

    def _transaction(self, work):
        for attempt in range(self.max_retries+1):
            conn=self.connection_factory()
            try:
                with conn.cursor() as c: result=work(c)
                conn.commit(); return result
            except Exception as exc:
                conn.rollback(); code=getattr(exc,"args",[None])[0]
                if code in _RETRYABLE and attempt < self.max_retries:
                    time.sleep(0.01*(2**attempt)); continue
                if code in _RETRYABLE: raise RepositoryUnavailable("database lock retry exhausted") from exc
                raise
            finally: conn.close()

    def _begin_idempotency(self,c,key,command):
        if not key: raise KnowledgeUnitValidationError("idempotency_key is required")
        digest=_command_hash(command)
        c.execute("SELECT command_hash,logical_id,revision_id FROM idempotency_records WHERE tenant_id=%s AND request_id=%s FOR UPDATE",(self.tenant_id,key))
        row=c.fetchone()
        if row:
            if bytes(row["command_hash"]) != digest: raise KnowledgeUnitConflictError("idempotency key reused with different command")
            return {"logical_id":_text(row["logical_id"])} if row.get("logical_id") else None
        c.execute("INSERT INTO idempotency_records(tenant_id,request_id,command_hash,state,created_at) VALUES(%s,%s,%s,'STARTED',%s)",(self.tenant_id,key,digest,_now()))
        return None

    def _finish_idempotency(self,c,key,lid,rid):
        c.execute("UPDATE idempotency_records SET state='COMMITTED',logical_id=%s,revision_id=%s,completed_at=%s WHERE tenant_id=%s AND request_id=%s",(_id(lid),_id(rid),_now(),self.tenant_id,key))

    def _insert_revision(self,c,lid,rid,no,status,draft,actor,now):
        c.execute("INSERT INTO knowledge_revisions(tenant_id,revision_id,logical_id,revision_no,status,claim_json,scope_json,language_json,confidence,content_hash,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(self.tenant_id,_id(rid),_id(lid),no,status,_json(draft.get("claim",{})),_json(draft.get("scope",{})),_json(draft.get("language",{})),draft.get("confidence",0),_command_hash({k:draft.get(k) for k in ("claim","scope","language")}),str(actor),now))

    def _event_outbox(self,c,lid,rid,no,old,new,actor,key,now):
        c.execute("INSERT INTO knowledge_events(tenant_id,event_id,logical_id,revision_id,from_status,to_status,actor_id,request_id,occurred_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",(self.tenant_id,uuid.uuid4().bytes,_id(lid),_id(rid),old,new,str(actor),key,now))
        c.execute("INSERT INTO knowledge_outbox(tenant_id,outbox_id,aggregate_id,aggregate_version,event_type,payload_json,created_at,available_at) VALUES(%s,%s,%s,%s,'knowledge.changed',%s,%s,%s)",(self.tenant_id,uuid.uuid4().bytes,_id(lid),no,_json({"tenant_id":self.tenant_id,"logical_id":lid,"revision_id":rid,"status":new}),now,now))

    def _read_one(self,where,args):
        conn=self.connection_factory()
        try:
            with conn.cursor() as c: c.execute(self._select()+" "+where,args); row=c.fetchone()
            if not row: raise KnowledgeUnitNotFoundError(args[-1])
            return self._decode(row)
        finally: conn.close()

    @staticmethod
    def _select(): return "SELECT h.lock_version,r.* FROM knowledge_revisions r JOIN knowledge_heads h ON h.tenant_id=r.tenant_id AND h.logical_id=r.logical_id"
    @staticmethod
    def _decode(row):
        if not isinstance(row,dict): raise TypeError("DictCursor-compatible connection required")
        x=dict(row); x["logical_id"],x["revision_id"]=_text(x["logical_id"]),_text(x["revision_id"])
        for src,dst in (("claim_json","claim"),("scope_json","scope"),("language_json","language")):
            value=x.pop(src); x[dst]=json.loads(value) if isinstance(value,(str,bytes,bytearray)) else value
        x["revision_no"]=int(x["revision_no"]); return x
    @staticmethod
    def _validate_draft(draft):
        if not draft.get("claim") or not draft.get("scope") or not draft.get("language"): raise KnowledgeUnitValidationError("claim, scope, and language are required")
