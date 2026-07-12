# LCE v0.1 Independent Holdout A

## Purpose

This document defines the first independent-evaluation lane for the local HTTP
Control API. It measures narrow API-gate behavior. It does not measure general
chat quality, world knowledge, safety, or LLM equivalence.

The public repository contains this plan and a metadata-only manifest. The
held-out inputs, gold decisions, model outputs, and repair targets remain in a
separate evaluator-held private repository. Keeping those materials out of the
implementation repository is a prerequisite for an independent result.

## Questions

For the same frozen cases, what changes when a caller uses the LCE gate?

```text
lce_only       The gate evaluates a supplied candidate without an LLM call.
lm_only        The caller accepts the model candidate without LCE review.
lm_with_lce    The caller submits the model candidate to LCE before deciding.
```

The comparison is task-specific. An `ACCEPT` means that the declared contract
passed; it is not a claim that the response is factually true, safe, or useful.

## Frozen Suite Contract

| Track | Cases | Primary question |
|---|---:|---|
| Structured output | 60 | Does the route preserve a declared response contract and identify repair/hold outcomes? |
| Candidate and authorization | 40 | Does the route avoid accepting candidates outside declared evidence or authorization bounds? |
| Acceptance challenge | 25 | Does the route surface a justified challenge rather than clearing an unsupported acceptance? |
| **Total** | **125** | Bounded API-gate comparison only. |

Each track includes both English and Japanese materials where the contract
permits language-bearing content. The corpus must include valid, malformed,
ambiguous, insufficient-evidence, and adversarial-but-in-scope cases. It must
not reuse public regression fixtures as holdout cases.

## Custody and Independence

1. An evaluator creates the cases and gold outcomes in a private repository
   that is not accessible to LCE implementation authors during development.
2. The evaluator freezes the corpus before a comparison run, records the
   private revision and an archive digest, and retains the mapping from case ID
   to outcome privately.
3. Only the manifest schema, track counts, variant names, aggregate metrics,
   archive digest, evaluator role, and run environment may be published.
4. A model-generated candidate cannot become independent gold without
   provenance, quarantine, and a reviewer who is independent from both model
   prompting and LCE implementation.
5. Any change to LCE, the model, adapter/profile, contract, or corpus requires
   a new run. The prior run remains historical evidence only.

The evaluator may disclose de-identified failure classes after a completed
run, but must not disclose enough input/output detail to turn the held-out set
into a development fixture.

## Measurements

For every track and comparison variant, publish:

- case count and evaluated count;
- accepted, returned-to-model, and held decisions;
- false accepts and false holds/rejects against the private gold outcome;
- contract-decision match rate;
- repair-return rate when a repair loop is applicable;
- LCE gate latency in milliseconds (`p50` and `p95`);
- LCE version/commit, Python version, operating-system family, model ID/digest,
  adapter/profile ID, and input-contract ID.

`lm_only` must use the same candidate and decision semantics as the caller
would otherwise use. The evaluator must record that baseline decision rule.
`lce_only` is not a language-model quality baseline; it exists to isolate gate
behavior over supplied candidates.

## Release Acceptance Targets

These are release targets for this narrowly defined suite, not universal
safety guarantees:

| Metric | Target |
|---|---:|
| Critical evidence/authorization false accepts | 0 |
| False holds/rejects | <= 10% |
| Contract-decision match rate | >= 95% |
| Manifest and custody audit | 100% complete |

If a target is missed, publish the miss as a bounded result, classify the
failure, and do not recast the affected lane as assured. A target met on this
suite permits only the statement that the specified version met the target on
the specified frozen evaluation.

## Public Artifacts and First Run

[`evaluation/holdout_manifest_v1.json`](evaluation/holdout_manifest_v1.json)
is intentionally metadata-only and is checked by
[`scripts/verify_holdout_manifest.py`](scripts/verify_holdout_manifest.py).
The first evaluator-held corpus and its comparison result remain release work;
this plan alone is not an independent evaluation result.

See [EVALUATION_POLICY.md](EVALUATION_POLICY.md) for the broader evidence
taxonomy and [RELEASE_READINESS.md](RELEASE_READINESS.md) for release gates.
