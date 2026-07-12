from __future__ import annotations

from typing import Any


def unknown_provenance(source_id: str, *, use_class: str = "internal_validation") -> dict[str, Any]:
    return {
        "provenance_id": f"prov-{source_id}",
        "source_id": source_id,
        "source_url_or_path": "unknown",
        "source_version": "unknown",
        "retrieved_at": "unknown",
        "raw_hash": "unknown",
        "normalized_hash": "unknown",
        "license_ref": "license_unknown",
        "contamination_ref": "contamination_unknown",
        "lineage_refs": [],
        "freshness_status": "unknown",
        "coverage_boundary": "unknown",
        "use_class": use_class,
    }
