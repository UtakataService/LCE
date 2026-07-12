from __future__ import annotations

import os
import time
from typing import Any


def sample_resource(run_id: str) -> dict[str, Any]:
    return {
        "resource_snapshot_ref": f"res-{run_id}-{int(time.time())}",
        "run_id": run_id,
        "timestamp": time.time(),
        "cpu_percent": None,
        "memory_bytes": None,
        "disk_read_bytes": None,
        "disk_write_bytes": None,
        "network_bytes": None,
        "gpu_utilization": None,
        "vram_bytes": None,
        "thermal_status": "not_sampled",
        "sampler_id": f"stdlib-dryrun-{os.getpid()}",
    }
