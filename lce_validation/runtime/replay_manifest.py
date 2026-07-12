from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _event_hash(row: dict[str, Any]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_replay_manifest(run_id: str, events: list[dict[str, Any]], artifact_refs: list[dict[str, Any]]) -> dict[str, Any]:
    event_ids = [row.get("event_id") for row in events]
    return {
        "replay_manifest_id": f"replay-{run_id}",
        "run_id": run_id,
        "event_range": [event_ids[0], event_ids[-1]] if event_ids else [],
        "event_hashes": [_event_hash(row) for row in events],
        "artifact_hash_refs": artifact_refs,
        "state_versions": [row.get("state_version") for row in events if row.get("state_version")],
        "resource_snapshot_refs": [row.get("resource_snapshot_ref") for row in events if row.get("resource_snapshot_ref")],
        "watchdog_refs": [row.get("watchdog_ref") for row in events if row.get("watchdog_ref")],
        "known_gaps": [],
        "redaction_records": [],
        "rebuild_command_ref": "python -m lce_validation.cli run-smoke",
        "replay_status": "manifest_present",
    }


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
