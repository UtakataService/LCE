# Contributing to LCE

LCE is an experimental Open Core for bounded judgement, verification, and
control around optional language models and tools. Contributions are welcome
when they preserve explicit boundaries and reproducible evidence.

## Before Opening a Change

1. Read `CURRENT_STATUS.md` and keep claims within its stated boundaries.
2. Keep model, Pack, and adapter behavior separate from Core invariants.
3. Add focused tests for behavioral changes. Do not rewrite unrelated files.
4. Record fixtures, provenance, and evaluation boundaries for new quality
   claims.

## Contribution Rules

- Packs are data only. They cannot introduce executable hooks that bypass Core
  validation, authorization, state bounds, trace integrity, or replay rules.
- A passing closed fixture is not evidence of general intelligence, truth,
  safety, or production readiness.
- New integrations must fail closed when an authorization, schema, or evidence
  requirement is unavailable.
- Do not add training data or scraped content without documented provenance,
  license, and intended-use metadata.

## Pull Requests

Describe the problem, the bounded claim, files changed, test command, observed
result, and known limitations. For policy changes, include at least one
negative or adversarial fixture.

## License Status

Contributions are accepted only under the repository `LICENSE`. Individual
contributions do not grant Organizational use rights beyond the terms stated
there. See `LICENSE_POLICY.md` and `ORGANIZATIONAL_USE.md`.
