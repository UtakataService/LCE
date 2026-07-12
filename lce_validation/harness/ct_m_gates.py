from __future__ import annotations

from typing import Any


def gate_result(gate_id: str, row_id: str, fixture_id: str, *, triggered: bool, block_condition: bool, reason: str) -> dict[str, Any]:
    return {
        "gate_result_id": f"{gate_id}-{row_id}",
        "gate_id": gate_id,
        "row_id": row_id,
        "fixture_id": fixture_id,
        "triggered": triggered,
        "result": "fail" if block_condition else "pass",
        "expected_non_accepting_behavior": "reject_or_repair_if_triggered",
        "actual_behavior_ref": "dry_run",
        "block_condition": block_condition,
        "reason": reason,
    }
