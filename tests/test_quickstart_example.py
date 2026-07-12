import runpy
from pathlib import Path


def test_open_core_quickstart_runs_the_bundled_reference_contract():
    root = Path(__file__).resolve().parents[1]
    namespace = runpy.run_path(str(root / "examples" / "quickstart_open_core.py"))
    result = namespace["run"]()
    assert result["profile_lock"].startswith("sha256:")
    assert result["conformance_passed"] == 8
    assert result["conformance_failed"] == 0
    assert result["shadow_equal"] == 8
    assert result["shadow_different"] == 0
