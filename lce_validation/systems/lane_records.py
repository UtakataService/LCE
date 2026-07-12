from __future__ import annotations

from typing import Any


def lane_row(run_id: str, process_identity_ref: str, resource_snapshot_ref: str, lane_label: str = "WIN_CPU_FIRST") -> dict[str, Any]:
    return {
        "lane_row_id": f"lane-{run_id}",
        "run_id": run_id,
        "lane_label": lane_label,
        "host_id": "windows-local",
        "gpu_assist": False,
        "process_identity_ref": process_identity_ref,
        "resource_snapshot_refs": [resource_snapshot_ref],
        "replay_manifest_ref": f"replay-{run_id}",
        "status": "dry_run",
    }
