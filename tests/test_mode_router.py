from lce_validation.runtime.mode_router import select_mode
from lce_validation.web_ui import dispatch_response


def test_router_prefers_structured_contract():
    decision=select_mode({"text":"Return JSON", "schema":{"type":"object"}})
    assert decision["mode"]=="structured"


def test_router_sends_safety_to_daily_boundary():
    decision=select_mode({"text":"I want to kill myself"})
    assert decision["mode"]=="daily_dialogue"
    assert "safety_boundary_signal" in decision["reasons"]


def test_auto_dispatch_records_decision():
    result=dispatch_response({"mode":"auto","text":"I am only venting. Please do not give advice yet.","history":[]})
    assert result["selected_mode"]=="daily_dialogue"
    assert result["routing"]["mode"]=="daily_dialogue"


def test_router_defaults_to_bounded_daily_dialogue():
    assert select_mode({"text":"hello"})["mode"]=="daily_dialogue"
