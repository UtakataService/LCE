import json
from pathlib import Path

from lce_validation.runtime.utterance_frame import frame_utterance, frame_utterance_legacy


def test_reference_frame_pack_has_dual_run_parity_with_frozen_legacy_table():
    path = Path("lce_validation/fixtures/open_core_frame_parity_v1.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert {row["language"] for row in rows} == {"en", "ja"}
    for row in rows:
        active = frame_utterance(row["text"])
        legacy = frame_utterance_legacy(row["text"])
        assert active == legacy, row["case_id"]
