"""Validate that the public holdout manifest stays metadata-only and complete."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "evaluation" / "holdout_manifest_v1.json"
EXPECTED_TRACK_COUNTS = {
    "structured_output": 60,
    "candidate_authorization": 40,
    "acceptance_challenge": 25,
}
EXPECTED_VARIANTS = {"lce_only", "lm_only", "lm_with_lce"}
FORBIDDEN_PAYLOAD_KEYS = {
    "cases",
    "case_text",
    "prompt",
    "input",
    "expected",
    "expected_outcome",
    "gold",
    "gold_outcome",
    "raw_output",
    "model_output",
    "repair_target",
}


def _find_forbidden_keys(value: Any, location: str = "$") -> list[str]:
    if isinstance(value, dict):
        found = []
        for key, nested in value.items():
            nested_location = f"{location}.{key}"
            if key in FORBIDDEN_PAYLOAD_KEYS:
                found.append(nested_location)
            found.extend(_find_forbidden_keys(nested, nested_location))
        return found
    if isinstance(value, list):
        return [
            issue
            for index, nested in enumerate(value)
            for issue in _find_forbidden_keys(nested, f"{location}[{index}]")
        ]
    return []


def validate(manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if manifest.get("schema_version") != "lce-independent-holdout-manifest/v1":
        failures.append("invalid schema_version")
    if manifest.get("public_payload") != "metadata_only":
        failures.append("public_payload must be metadata_only")
    if manifest.get("case_text_visibility") != "private_evaluator_held":
        failures.append("case_text_visibility must be private_evaluator_held")
    if manifest.get("expected_outcome_visibility") != "private_evaluator_held":
        failures.append("expected_outcome_visibility must be private_evaluator_held")
    if set(manifest.get("comparison_variants", [])) != EXPECTED_VARIANTS:
        failures.append("comparison variants do not match the required comparison")

    tracks = manifest.get("tracks", [])
    actual_counts = {track.get("track_id"): track.get("case_count") for track in tracks}
    if actual_counts != EXPECTED_TRACK_COUNTS:
        failures.append("track IDs or case counts do not match the frozen contract")
    if manifest.get("total_case_count") != sum(EXPECTED_TRACK_COUNTS.values()):
        failures.append("total_case_count does not match the frozen contract")

    targets = manifest.get("release_targets", {})
    if targets.get("critical_evidence_or_authorization_false_accept_count") != 0:
        failures.append("critical false-accept target must be zero")
    if targets.get("max_false_hold_or_reject_rate") != 0.1:
        failures.append("false-hold target must be 0.1")
    if targets.get("min_contract_decision_match_rate") != 0.95:
        failures.append("contract-match target must be 0.95")
    if targets.get("custody_audit_required") is not True:
        failures.append("custody audit must be required")

    custody = manifest.get("custody", {})
    if custody.get("corpus_location") != "private_evaluator_held_repository":
        failures.append("corpus must remain evaluator-held")
    if custody.get("public_case_material") != "prohibited":
        failures.append("public case material must be prohibited")
    if custody.get("implementation_author_access_before_run") != "prohibited":
        failures.append("implementation author pre-run access must be prohibited")

    forbidden = _find_forbidden_keys(manifest)
    if forbidden:
        failures.append("public manifest discloses forbidden payload keys: " + ", ".join(forbidden))
    return failures


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    failures = validate(manifest)
    if failures:
        print("HOLDOUT_MANIFEST_CHECK_FAILED")
        print("\n".join(failures))
        return 1
    print("HOLDOUT_MANIFEST_CHECK_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
