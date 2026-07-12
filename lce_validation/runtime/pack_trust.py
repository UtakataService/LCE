"""Explicit Pack trust-store checks for the experimental Open Core.

This is a trust-pinning and revocation foundation. It does not claim detached
public-key signature verification; a public release must add a verifier for the
trust-store distribution and Pack signatures before third-party distribution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .model_pack import PackValidationError, validate_pack


class PackTrustError(PackValidationError):
    pass


@dataclass(frozen=True, slots=True)
class TrustedPackIdentity:
    pack_id: str
    pack_version: str
    content_hash: str
    issuer_id: str
    key_id: str
    status: str = "active"


@dataclass(frozen=True, slots=True)
class PackTrustStore:
    store_id: str
    store_version: str
    identities: tuple[TrustedPackIdentity, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PackTrustStore":
        if not isinstance(value, Mapping) or not isinstance(value.get("identities"), list):
            raise PackTrustError("INVALID_PACK_TRUST_STORE")
        identities = tuple(_identity_from_dict(item) for item in value["identities"])
        store = cls(value.get("store_id", ""), value.get("store_version", ""), identities)
        _validate_store(store)
        return store


def require_trusted_pack(pack: Mapping[str, Any], trust_store: PackTrustStore | Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Pack then require an active, exact identity pin."""
    validate_pack(pack)
    store = trust_store if isinstance(trust_store, PackTrustStore) else PackTrustStore.from_dict(trust_store)
    key = (pack["pack_id"], pack["pack_version"], pack["content_hash"])
    matches = [entry for entry in store.identities if (entry.pack_id, entry.pack_version, entry.content_hash) == key]
    if not matches:
        raise PackTrustError("PACK_IDENTITY_UNTRUSTED")
    entry = matches[0]
    if entry.status == "revoked":
        raise PackTrustError("PACK_IDENTITY_REVOKED")
    return {
        "trusted": True,
        "store_id": store.store_id,
        "store_version": store.store_version,
        "pack_id": entry.pack_id,
        "pack_version": entry.pack_version,
        "content_hash": entry.content_hash,
        "issuer_id": entry.issuer_id,
        "key_id": entry.key_id,
        "claim_boundary": "Exact identity pin and revocation check only. This module does not verify a detached public-key signature or establish trust in the trust-store distribution.",
    }


def _identity_from_dict(value: Mapping[str, Any]) -> TrustedPackIdentity:
    if not isinstance(value, Mapping):
        raise PackTrustError("INVALID_TRUSTED_PACK_IDENTITY")
    identity = TrustedPackIdentity(
        pack_id=value.get("pack_id", ""),
        pack_version=value.get("pack_version", ""),
        content_hash=value.get("content_hash", ""),
        issuer_id=value.get("issuer_id", ""),
        key_id=value.get("key_id", ""),
        status=value.get("status", "active"),
    )
    if not all(isinstance(item, str) and item for item in (identity.pack_id, identity.pack_version, identity.content_hash, identity.issuer_id, identity.key_id)) or not identity.content_hash.startswith("sha256:") or identity.status not in {"active", "revoked"}:
        raise PackTrustError("INVALID_TRUSTED_PACK_IDENTITY")
    return identity


def _validate_store(store: PackTrustStore) -> None:
    if not isinstance(store.store_id, str) or not store.store_id or not isinstance(store.store_version, str) or not store.store_version or not store.identities:
        raise PackTrustError("INVALID_PACK_TRUST_STORE")
    keys = [(entry.pack_id, entry.pack_version, entry.content_hash) for entry in store.identities]
    if len(keys) != len(set(keys)):
        raise PackTrustError("DUPLICATE_TRUSTED_PACK_IDENTITY")
