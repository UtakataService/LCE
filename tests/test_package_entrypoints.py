from __future__ import annotations

import subprocess
import sys

import lce_validation


def test_python_module_entrypoint_exposes_cli_help() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "lce_validation", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "run-public-readiness-evidence" in completed.stdout


def test_runtime_version_matches_package_release() -> None:
    assert lce_validation.__version__ == "0.1.0a1"
