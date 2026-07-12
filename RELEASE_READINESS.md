# v0.1.0-alpha Release Readiness

## Release Definition

**Experimental Open Core + Reference Pack + Reference Assurance Gateway**.

This release is a reproducible control-layer reference, not an LLM, a hosted
service, a general safety product, or a third-party plugin platform.

## GO Gates

| Gate | Required evidence | Current state |
|---|---|---|
| Scope and non-claims | README, overview, status, and examples say the same thing | GO on the verified working checkout. |
| Reproducible reference path | Fresh Python 3.11 run of both reference examples | GO on the verified working checkout; repeat from a clean release checkout. |
| Regression evidence | Full test suite and public-readiness command recorded with exact versions | GO on the verified working checkout; repeat for the release tag. |
| LLM reference integration | A caller-owned HTTP Control API and a recorded `lm_only` / `lm_with_lce` contract comparison | GO on the release candidate: versioned `gemma4:e4b` profile and same-candidate demo are included. |
| Evaluation integrity | Fixed evidence clearly labeled; an independent holdout plan published | Plan GO; first evaluator-held corpus and comparison run remain pending. |
| Community health | Contribution, security, support, conduct, issue/PR templates present | GO; contact form is published for security and Organization-use requests. |
| License | Bundled license and matching package metadata | GO for source-available release; Organization contact route is published. |
| Release artifact | Tagged source archive, checksum, release notes, and known-limit list | GO locally: ZIP, SHA-256, release notes, and clean-checkout evidence are prepared. GitHub publication remains pending repository owner/remote setup. |

## Release Blockers

1. Create the public GitHub repository `LCE`, push the staged candidate, tag
   `v0.1.0-alpha`, and upload the generated ZIP and SHA-256 file.
2. Run the independent holdout through an evaluator-held corpus before claiming
   any comparative uplift.

The current integrity evidence is in
`outputs/public-readiness-release-integrity-20260712/`. It contains the three
fixed public-readiness suites; its scope remains bounded by
`EVALUATION_POLICY.md`.

## Deliberate Exclusions

- Third-party Pack download and distribution: signature/key lifecycle is absent.
- Arbitrary tool execution, auto-routing replacement, and public web service.
- General dialogue, factuality, safety, or 20B-quality claims.
- Production Pi deployment.

## Release Procedure

1. Run the commands in [QUICKSTART.md](QUICKSTART.md) and the full regression
   suite on the release checkout.
2. Regenerate the public-readiness evidence and record the exact command and
   results in `CURRENT_STATUS.md`.
3. Verify the documentation links and examples from a clean checkout.
4. Build `dist/LCE-0.1.0-alpha.zip`, verify its SHA-256, and retain the clean
   checkout evidence.
5. Create the GitHub release only after the license/contact policy, release
   artifact, and documentation integrity gate are all GO.
