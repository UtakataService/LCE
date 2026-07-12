from __future__ import annotations

import os
import sys
from typing import Any


def current_process_identity(host_id: str = "windows-local") -> dict[str, Any]:
    return {
        "process_identity_ref": f"proc-{os.getpid()}",
        "host_id": host_id,
        "pid": os.getpid(),
        "parent_pid": None,
        "executable_path": sys.executable,
        "command_line_hash": "dry_run",
        "start_time": "unknown",
        "port_refs": [],
    }
