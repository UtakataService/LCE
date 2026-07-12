import json
from pathlib import Path

from lce_validation.runtime.model_pack import load_pack
from lce_validation.runtime.runtime_profile import load_runtime_profile, reference_runtime_profile
from lce_validation.runtime.utterance_frame import frame_utterance


FIXTURES = Path("lce_validation/fixtures")


def test_reference_runtime_profile_is_recorded_in_the_frame():
    profile = reference_runtime_profile()
    frame = frame_utterance("Please just listen.", runtime_profile=profile)
    assert frame["runtime_profile"] == profile.trace_identity()


def test_runtime_profile_selects_the_pinned_language_pack(tmp_path):
    listen = load_pack(FIXTURES / "reference_language_pack_listen_v1.json")
    listen["capabilities"] = ["frame.core.v1"]
    semantic = json.loads((FIXTURES / "reference_semantic_cube_v1.json").read_text(encoding="utf-8"))
    (tmp_path / "alternate_listen.json").write_text(json.dumps(listen), encoding="utf-8")
    (tmp_path / "semantic.json").write_text(json.dumps(semantic), encoding="utf-8")
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({
        "schema_version": "lce-profile/v1",
        "profile_id": "test.alternate.listen",
        "profile_version": "1.0.0",
        "engine_compatibility": "lce-core/v1",
        "capabilities": ["frame.core.v1", "semantic.cube.dialogue.v1"],
        "pack_refs": [
            {key: listen[key] for key in ("pack_id", "pack_version", "content_hash")},
            {key: semantic[key] for key in ("pack_id", "pack_version", "content_hash")},
        ],
    }), encoding="utf-8")
    alternate = load_runtime_profile(profile_path, tmp_path)
    reference = frame_utterance("What should I do? I need advice.")
    selected = frame_utterance("What should I do? I need advice.", runtime_profile=alternate)
    assert "sem.interaction.advice_permitted" in reference["semantic_ids"]
    assert "sem.interaction.advice_permitted" not in selected["semantic_ids"]
    assert selected["runtime_profile"]["profile_id"] == "test.alternate.listen"
