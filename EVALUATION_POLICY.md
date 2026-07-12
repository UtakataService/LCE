# Evaluation Policy

## Purpose

LCE evaluation must distinguish contract regression from model quality. A
passing fixed fixture proves only that a declared implementation contract still
behaves as expected for that fixture.

Closed fixtures are regression evidence only. They do not establish general
language understanding, factuality, safety, or model-quality parity.

## Evidence Classes

| Class | Use | Permitted claim |
|---|---|---|
| Development fixture | Design and regression | Implementation behavior only. |
| Fixed holdout | Regression outside the immediate edit set | Bounded holdout behavior only. |
| Independent holdout | A separately authored, custody-tracked comparison set | Narrow comparative result with its exact task. |
| Blind/sealed evaluation | Release evaluator-held data | Generalization claim only within the measured track. |
| Live integration probe | Versioned model/adapter/profile run | Integration behavior only. |

## Required Comparison Modes

Any claim that LCE improves a model-backed workflow must compare the same cases
under:

```text
lce_only
lm_only
lm_with_lce
```

Record model ID/digest, adapter/profile, input contract, fixture custody,
accepted/rejected outcome, repair count, false accepts, false rejects, and
latency. A model or LCE change requires a new run.

## Publication Rules

- Do not infer general chat quality, factuality, safety, or 20B equivalence
  from closed fixtures.
- Publish known safe limits and false-positive/false-negative counts whenever
  the task supports measuring them.
- Treat a structural accept as distinct from factual truth, authorization, and
  policy approval.
- Never use model-authored material as independent evaluation gold without
  quarantine, provenance, and an independent reviewer.
- Keep external web data, training candidates, and third-party Packs out of
  public promoted data until provenance, license, and trust gates pass.

## v0.1.0-alpha Evaluation Gate

The public alpha must publish its exact regression command, fixed-evidence
scope, a Gemma E4B reference comparison, and an independent-holdout plan. It
must not claim generalization until the independent and blind lanes exist.

The metadata-only contract for the first API-gate holdout is in
[EVALUATION_HOLDOUT_PLAN.md](EVALUATION_HOLDOUT_PLAN.md). Publishing the plan
does not convert it into a result: cases and gold outcomes remain
evaluator-held until an independent run is completed.
