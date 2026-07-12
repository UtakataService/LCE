from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_contract_documents_expose_experimental_and_license_boundaries():
    required = {
        "CONTRIBUTING.md": "experimental",
        "SECURITY.md": "experimental",
        "CODE_OF_CONDUCT.md": "respectful",
        "SUPPORT.md": "does not provide production SLA",
        "LICENSE_POLICY.md": "Personal and Organizational Use",
        "OPEN_SOURCE_ROADMAP_JA.md": "AB1",
    }
    for filename, marker in required.items():
        assert marker.casefold() in (ROOT / filename).read_text(encoding="utf-8").casefold()


def test_public_issue_surfaces_require_reproduction_and_capability_boundary():
    bug = (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").read_text(encoding="utf-8")
    feature = (ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml").read_text(encoding="utf-8")
    assert "Reproduction" in bug
    assert "CURRENT_STATUS.md" in bug
    assert "evaluation" in feature
