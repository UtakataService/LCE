"""Minimal reference application for LCE assurance gates.

It demonstrates three bounded outcomes without an LLM or network dependency:
an accepted structured candidate, an authorization hold, and a challenged
accepted result that must not be promoted yet.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lce_validation.runtime.acceptance_challenge import challenge_accepted_result
from lce_validation.runtime.candidate_assurance import assess_candidate


def run() -> dict[str, Any]:
    policy = {
        "policy_id": "reference-tool-plan-v1",
        "allowed_modalities": ["model"],
        "allowed_claim_types": ["tool_plan"],
        "min_confidence": 0.8,
        "required_evidence_kinds": ["request_trace"],
        "required_value_paths": {"tool": "calendar.read"},
        "allowed_action_scopes": ["display", "state_commit"],
    }
    evidence = {"request-1": {"evidence_id": "request-1", "kind": "request_trace", "source_digest": "sha256:request"}}
    base = {
        "candidate_id": "plan-1", "modality": "model", "claim_type": "tool_plan",
        "value": {"tool": "calendar.read"}, "confidence": 0.9,
        "evidence_refs": ["request-1"], "producer_id": "reference-adapter",
        "input_digest": "sha256:request", "action_scope": "display",
    }
    accepted = assess_candidate(base, policy, evidence)
    held = assess_candidate({**base, "candidate_id": "plan-2", "action_scope": "state_commit"}, policy, evidence)
    promotion = challenge_accepted_result(
        {"result_id": "plan-1", "decision": accepted["decision"], "evidence_refs": ["request-1"], "reviewer_keys": ["contract-check"], "cross_checks": {"schema": "fail"}},
        {"policy_id": "reference-promotion-v1", "required_cross_checks": ["schema"]},
        {"request-1": {"kind": "request_trace"}},
    )
    return {"candidate_accepted": accepted, "candidate_authorization_hold": held, "promotion_gate": promotion}


if __name__ == "__main__":
    result = run()
    print(f"candidate_accepted: {result['candidate_accepted']['decision']}")
    print(f"candidate_authorization_hold: {result['candidate_authorization_hold']['decision']}")
    print(f"promotion_gate: {result['promotion_gate']['decision']}")
