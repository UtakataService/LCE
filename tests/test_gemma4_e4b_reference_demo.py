from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gemma_reference_demo", ROOT / "examples" / "gemma4_e4b_reference_demo.py")
DEMO = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(DEMO)


def test_reference_profile_and_cases_load() -> None:
    profile, cases = DEMO.load_reference_inputs()

    assert profile["model_id"] == "gemma4:e4b"
    assert profile["generation_options"] == {"temperature": 0, "seed": 7}
    assert [case["language"] for case in cases] == ["en", "ja", "en"]


def test_same_candidate_comparison_keeps_structure_but_adds_evidence_gate() -> None:
    profile, _ = DEMO.load_reference_inputs()
    raw = '{"summary":"A budget conclusion.","certainty":"known","evidence_refs":[]}'

    result = DEMO.evaluate_same_candidate(raw, profile)

    assert result["lm_only"]["accepted"]
    assert result["lm_with_lce"]["status"] == "SEMANTIC_REJECTED"
    assert result["lm_with_lce"]["violations"] == ["CERTAINTY_EVIDENCE_REQUIRED_CLAIM_MISSING"]
