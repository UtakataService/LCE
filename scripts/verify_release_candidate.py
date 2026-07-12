"""Check the files and declarations required for the v0.1.0-alpha candidate."""
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "LICENSE",
    "RELEASE_NOTES_v0.1.0-alpha.md",
    "RELEASE_NOTES_v0.1.0-alpha.1.md",
    "PIP_INSTALL.md",
    "GEMMA4_E4B_REFERENCE.md",
    "EVALUATION_HOLDOUT_PLAN.md",
    "profiles/gemma4_e4b_reference_profile_v1.json",
    "examples/gemma4_e4b_reference_demo.py",
    "scripts/build_release_archive.py",
    "lce_validation/__main__.py",
}
CONTACT = "https://utakataservice.com/contact/contact.php"


def main() -> int:
    failures = [f"MISSING:{path}" for path in sorted(REQUIRED) if not (ROOT / path).is_file()]
    for path in ("SUPPORT.md", "SECURITY.md", "ORGANIZATIONAL_USE.md", "RELEASE_NOTES_v0.1.0-alpha.md"):
        if CONTACT not in (ROOT / path).read_text(encoding="utf-8"):
            failures.append(f"CONTACT_MISSING:{path}")
    if failures:
        print("RELEASE_CANDIDATE_CHECK_FAILED")
        print("\n".join(failures))
        return 1
    print("RELEASE_CANDIDATE_CHECK_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
