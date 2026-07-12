from pathlib import Path

from lce_validation.open_core import OpenCoreSdk


def test_experimental_sdk_locks_reference_profile_and_runs_conformance():
    fixtures = Path("lce_validation/fixtures")
    sdk = OpenCoreSdk(fixtures)
    locked = sdk.lock_profile(fixtures / "reference_profile_frame_v1.json")
    reference = locked["pack_refs"][0]
    report = sdk.run_language_conformance(
        reference["pack_id"], reference["pack_version"], reference["content_hash"], fixtures / "open_core_frame_parity_v1.jsonl"
    )
    assert report["failed"] == 0
    ledger = sdk.frame_shadow_difference_ledger(fixtures / "open_core_frame_parity_v1.jsonl")
    assert all(row["equal"] for row in ledger)
