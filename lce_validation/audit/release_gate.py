from __future__ import annotations

from typing import Any


def release_gate_row(package_ref: str, failed_checks: list[str], blocked_claims: list[str]) -> dict[str, Any]:
    return {
        "release_gate_id": f"release-{package_ref}",
        "package_ref": package_ref,
        "required_checks": ["schema_validation", "redline_scan", "replay_refs", "resource_refs"],
        "passed_checks": [],
        "failed_checks": failed_checks,
        "blocked_claims": blocked_claims,
        "decision": "schema_contract_ready" if not failed_checks else "not_ready",
        "next_action": "continue_poc_validation",
    }
