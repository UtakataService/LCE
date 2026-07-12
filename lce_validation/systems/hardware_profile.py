from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from typing import Any


def local_hardware_profile(lane_label: str = "WIN_CPU_FIRST") -> dict[str, Any]:
    total_memory = _total_memory_bytes()
    profile = {
        "lane_label": lane_label,
        "host_id": socket.gethostname(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "cpu_count_logical": os.cpu_count(),
        "memory_total_bytes": total_memory,
        "gpu": _nvidia_smi_profile(),
        "profile_source": "stdlib_plus_optional_nvidia_smi",
    }
    profile["readiness_notes"] = _readiness_notes(profile)
    return profile


def raspberry_pi_boundary_profile(
    host: str = "private-pi-host",
    ports: tuple[int, ...] = (8790, 8788),
    mode: str = "dry_run",
) -> dict[str, Any]:
    return {
        "lane_label": "RASPI5_BOUNDARY",
        "host_id": f"raspberry-pi-{host}",
        "host": host,
        "ports": list(ports),
        "mode": mode,
        "status": "not_measured" if mode == "dry_run" else "unsupported_mode",
        "impact": "none",
        "claim": "boundary_record_only",
        "blocked_claims": ["raspberry_pi_sufficiency", "thermal_stability", "service_impact_safety"],
    }


def _total_memory_bytes() -> int | None:
    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return int(pages * page_size)
        except (OSError, ValueError, AttributeError):
            return None
    try:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
    except Exception:
        return None
    return None


def _nvidia_smi_profile() -> dict[str, Any]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {"available": False, "reason": "nvidia-smi not found"}
    query = "name,memory.total,driver_version"
    try:
        result = subprocess.run(
            [exe, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
    except Exception as exc:
        return {"available": False, "reason": type(exc).__name__}
    if result.returncode != 0 or not result.stdout.strip():
        return {"available": False, "reason": result.stderr.strip() or "empty nvidia-smi output"}
    first = result.stdout.splitlines()[0]
    parts = [part.strip() for part in first.split(",")]
    return {
        "available": True,
        "name": parts[0] if len(parts) > 0 else "unknown",
        "memory_total_mb": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None,
        "driver_version": parts[2] if len(parts) > 2 else "unknown",
    }


def _readiness_notes(profile: dict[str, Any]) -> list[str]:
    notes = []
    if (profile.get("cpu_count_logical") or 0) >= 8:
        notes.append("logical_cpu_count_supports_local_validation_lane")
    if (profile.get("memory_total_bytes") or 0) >= 16 * 1024**3:
        notes.append("memory_supports_fixture_scale_validation")
    if profile.get("gpu", {}).get("available"):
        notes.append("gpu_detected_but_not_required_for_structural_runtime")
    return notes
