from __future__ import annotations

from typing import Any


def dry_run_pi_service_probe(host_id: str = "raspberry-pi") -> dict[str, Any]:
    return {
        "pi_probe_id": "pi-probe-dry-run",
        "host_id": host_id,
        "service_ports_checked": [8790, 8788],
        "service_live_before": "not_checked",
        "service_live_during": "not_checked",
        "service_live_after": "not_checked",
        "thermal_throttle_state": "not_checked",
        "impact_status": "dry_run_no_network_or_service_impact",
        "block_reason": "explicit_approval_required_before_pi_impacting_probe",
    }
