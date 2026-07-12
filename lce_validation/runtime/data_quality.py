"""Deterministic, fail-closed learning evidence quality gate."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlparse

POLICY_VERSION = "data-quality/v1"

class QualityResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True, slots=True)
class RawEvidence:
    evidence_id: str
    text: str
    source_uri: str
    license: str | None
    language: str | None
    consent: bool | None = None
    source_family: str | None = None
    parent_hashes: tuple[str, ...] = ()
    self_generated: bool = False
    deleted: bool = False

@dataclass(frozen=True, slots=True)
class QualityCheck:
    name: str
    result: QualityResult
    reasons: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class QualityReport:
    evidence_id: str
    policy_version: str
    snapshot_hash: str
    result: QualityResult
    candidate_eligible: bool
    checks: tuple[QualityCheck, ...]
    reason_codes: tuple[str, ...]

_SECRET = re.compile(r"(?i)(api[_-]?key|password|secret)\s*[:=]\s*\S+")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d -]{7,}\d)(?!\d)")
_MOJIBAKE = ("\ufffd", "Ã", "Â", "縺", "繧", "譁")
_LICENSES = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "MIT", "PUBLIC-DOMAIN"}
_LANGS = {"en", "ja", "vi", "und"}

def _snapshot(e: RawEvidence) -> str:
    payload = {k: getattr(e, k) for k in e.__dataclass_fields__}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

def canonical_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())

class DataQualityEvaluator:
    def __init__(self, *, known_hashes: set[str] | None = None, deleted_hashes: set[str] | None = None):
        self.known_hashes = set(known_hashes or ())
        self.deleted_hashes = set(deleted_hashes or ())

    def evaluate(self, e: RawEvidence) -> QualityReport:
        checks = (
            self._identity(e), self._content(e), self._source(e), self._license(e),
            self._language(e), self._privacy(e), self._lineage(e), self._consent(e),
        )
        reasons = tuple(reason for check in checks for reason in check.reasons)
        result = QualityResult.FAIL if any(c.result is QualityResult.FAIL for c in checks) else (
            QualityResult.UNKNOWN if any(c.result is QualityResult.UNKNOWN for c in checks) else QualityResult.PASS
        )
        return QualityReport(e.evidence_id, POLICY_VERSION, _snapshot(e), result,
                             result is QualityResult.PASS, checks, reasons)

    def _identity(self, e):
        return QualityCheck("identity", QualityResult.PASS if e.evidence_id.strip() else QualityResult.FAIL,
                            () if e.evidence_id.strip() else ("MISSING_EVIDENCE_ID",))
    def _content(self, e):
        text = canonical_text(e.text)
        bad = not text or len(text) < 4 or any(x in text for x in _MOJIBAKE)
        return QualityCheck("content", QualityResult.FAIL if bad else QualityResult.PASS,
                            ("EMPTY_SHORT_OR_MOJIBAKE",) if bad else ())
    def _source(self, e):
        parsed = urlparse(e.source_uri)
        ok = parsed.scheme in {"https", "http"} and bool(parsed.netloc)
        return QualityCheck("source", QualityResult.PASS if ok else QualityResult.UNKNOWN,
                            () if ok else ("SOURCE_UNVERIFIED",))
    def _license(self, e):
        if e.license is None: return QualityCheck("license", QualityResult.UNKNOWN, ("LICENSE_UNKNOWN",))
        ok = e.license.upper() in _LICENSES
        return QualityCheck("license", QualityResult.PASS if ok else QualityResult.FAIL,
                            () if ok else ("LICENSE_NOT_ALLOWED",))
    def _language(self, e):
        if not e.language or e.language not in _LANGS:
            return QualityCheck("language", QualityResult.UNKNOWN, ("LANGUAGE_UNVERIFIED",))
        if e.language == "und":
            return QualityCheck("language", QualityResult.UNKNOWN, ("LANGUAGE_UNKNOWN",))
        return QualityCheck("language", QualityResult.PASS)
    def _privacy(self, e):
        hit = _SECRET.search(e.text) or _EMAIL.search(e.text) or _PHONE.search(e.text)
        return QualityCheck("privacy", QualityResult.FAIL if hit else QualityResult.PASS,
                            ("PII_OR_SECRET",) if hit else ())
    def _lineage(self, e):
        digest = "sha256:" + hashlib.sha256(canonical_text(e.text).encode("utf-8")).hexdigest()
        reasons=[]
        if digest in self.known_hashes: reasons.append("DUPLICATE_CONTENT")
        if e.self_generated: reasons.append("SELF_GENERATED")
        if e.deleted or any(h in self.deleted_hashes for h in e.parent_hashes): reasons.append("DELETED_LINEAGE")
        if digest in e.parent_hashes: reasons.append("CIRCULAR_LINEAGE")
        return QualityCheck("lineage", QualityResult.FAIL if reasons else QualityResult.PASS, tuple(reasons))
    def _consent(self, e):
        if e.consent is None: return QualityCheck("consent", QualityResult.UNKNOWN, ("CONSENT_UNKNOWN",))
        return QualityCheck("consent", QualityResult.PASS if e.consent else QualityResult.FAIL,
                            () if e.consent else ("CONSENT_DENIED",))
