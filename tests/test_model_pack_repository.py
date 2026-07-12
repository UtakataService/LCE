from pathlib import Path

from lce_validation.runtime.model_pack import load_pack
from lce_validation.runtime.model_pack_repository import (
    JsonPackRepository,
    build_frame_difference_ledger,
    load_profile,
    lock_profile_from_repository,
    run_language_pack_conformance,
    write_difference_ledger,
)


FIXTURE_DIR = Path("lce_validation/fixtures")
FRAME_PACK_PATH = FIXTURE_DIR / "reference_language_pack_frame_v1.json"
PARITY_PATH = FIXTURE_DIR / "open_core_frame_parity_v1.jsonl"


def test_repository_resolves_profile_pinned_frame_pack():
    repository = JsonPackRepository(FIXTURE_DIR)
    profile = load_profile(FIXTURE_DIR / "reference_profile_frame_v1.json")
    locked = lock_profile_from_repository(profile, repository)
    assert locked["profile_id"] == "org.lce.reference.frame"
    assert locked["pack_refs"][0]["pack_id"] == "org.lce.reference.language.frame"


def test_reference_pack_conformance_and_difference_ledger_are_clean(tmp_path):
    report = run_language_pack_conformance(load_pack(FRAME_PACK_PATH), PARITY_PATH)
    assert report["fixture_count"] == 8
    assert report["failed"] == 0
    ledger = build_frame_difference_ledger(PARITY_PATH)
    assert all(row["equal"] and not row["difference_fields"] for row in ledger)
    out = tmp_path / "difference.jsonl"
    write_difference_ledger(out, ledger)
    assert "今は愚痴" not in out.read_text(encoding="utf-8")
