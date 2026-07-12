from lce_validation.runtime.process_governance_practice import evaluate_process_governance_practice


def _record():
    return {"stages":[{"stage_id":"s1","status":"complete","completion_evidence":"test","depends_on":[]}],"purpose":{"original":"verify","current":"verify","drift_detected":False,"action":"continue"},"authority_impact":{"actor_authorized":True,"impact_classes":["reversible"],"rollback_or_mitigation":"revert"},"provenance":[{"source_id":"local","obtained_at":"2026-01-01","status":"verified","license_or_basis":"local"}],"decision_action":"execute"}


def test_ordered_authorized_verified_process_is_go(): assert evaluate_process_governance_practice(_record())["decision"] == "GO"
def test_purpose_drift_requires_hold_or_switch():
    r=_record(); r["purpose"].update({"drift_detected":True,"action":"continue"})
    assert "PURPOSE_DRIFT_NOT_HANDLED" in evaluate_process_governance_practice(r)["reasons"]
def test_high_impact_requires_authority_and_mitigation():
    r=_record(); r["authority_impact"]={"actor_authorized":False,"impact_classes":["irreversible"],"rollback_or_mitigation":""}
    assert "HIGH_IMPACT_AUTHORITY_OR_MITIGATION_MISSING" in evaluate_process_governance_practice(r)["reasons"]
