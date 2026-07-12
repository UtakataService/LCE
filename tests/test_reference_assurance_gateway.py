import runpy
from pathlib import Path


def test_reference_assurance_gateway_exposes_accept_hold_and_block_outcomes():
    root = Path(__file__).resolve().parents[1]
    namespace = runpy.run_path(str(root / "examples" / "reference_assurance_gateway.py"))
    result = namespace["run"]()
    assert result["candidate_accepted"]["decision"] == "ACCEPT"
    assert result["candidate_authorization_hold"]["decision"] == "HOLD"
    assert "AUTHORIZATION_REQUIRED" in result["candidate_authorization_hold"]["reasons"]
    assert result["promotion_gate"]["decision"] == "BLOCK"
