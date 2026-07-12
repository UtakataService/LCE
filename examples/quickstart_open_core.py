"""Run the smallest reproducible LCE Open Core reference path."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lce_validation.open_core import OpenCoreSdk


def run() -> dict[str, Any]:
    fixtures = ROOT / "lce_validation" / "fixtures"
    sdk = OpenCoreSdk(fixtures)
    locked = sdk.lock_profile(fixtures / "reference_profile_frame_v1.json")
    reference = locked["pack_refs"][0]
    report = sdk.run_language_conformance(
        reference["pack_id"],
        reference["pack_version"],
        reference["content_hash"],
        fixtures / "open_core_frame_parity_v1.jsonl",
    )
    ledger = sdk.frame_shadow_difference_ledger(fixtures / "open_core_frame_parity_v1.jsonl")
    return {
        "profile_lock": locked["profile_lock_hash"],
        "conformance_passed": report["passed"],
        "conformance_failed": report["failed"],
        "shadow_equal": sum(row["equal"] for row in ledger),
        "shadow_different": sum(not row["equal"] for row in ledger),
    }


if __name__ == "__main__":
    result = run()
    print(f"profile_lock: {result['profile_lock']}")
    print(f"conformance: {result['conformance_passed']} passed, {result['conformance_failed']} failed")
    print(f"shadow_ledger: {result['shadow_equal']} equal, {result['shadow_different']} different")
