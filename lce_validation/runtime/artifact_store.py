from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def hash_bytes(data: bytes, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    h.update(data)
    return h.hexdigest()


def record_artifact(path: str | Path, *, artifact_ref: str | None = None) -> dict[str, Any]:
    p = Path(path)
    data = p.read_bytes()
    return {
        "artifact_ref": artifact_ref or p.name,
        "artifact_path": str(p),
        "hash_algorithm": "sha256",
        "hash_value": hash_bytes(data),
        "byte_length": len(data),
        "created_by": "lce_validation",
        "source_event_ids": [],
        "retention_class": "internal_validation",
        "redaction_state": "none",
    }
