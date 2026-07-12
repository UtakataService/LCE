from lce_validation.runtime.interpretation_slice import run_interpretation_slice
from lce_validation.web_ui import dispatch_response


def test_listening_request_stays_tentative_and_reflects():
    result=run_interpretation_slice("I am tired. Please just listen for now.")
    assert result["response_steps"][0]["kind"]=="reflect"
    assert any(item["hypothesis"]=="requests_listening" for item in result["interpretation_set"])


def test_correction_replaces_prior_tentative_interpretation():
    first=run_interpretation_slice("I am stressed")
    second=run_interpretation_slice("Actually, that is not what I meant.",[{"interpretation_state":first["interpretation_state"]}])
    assert second["uptake"]=="CORRECTION"
    assert any(item["hypothesis"]=="corrects_prior_interpretation" for item in second["interpretation_set"])


def test_web_mode_dispatches_slice():
    result=dispatch_response({"mode":"interpretation","text":"愚痴を聞いてほしい","history":[]})
    assert result["mode"]=="bounded_interpretation_slice"
