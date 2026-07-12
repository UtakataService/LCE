# LCE Current Status

Last verified: 2026-07-12

This is the authoritative snapshot for public documentation. Historical files
under `outputs/` record their own run dates and do not override this document.

## Latest Verification

```text
Command: python -m pytest -q
Result: 548 passed, 4 skipped, 72 subtests passed
Duration: 8.82s
```

The four skipped tests are service-dependent lanes and are not successes.

## Bounded Evidence

| Area | Current evidence | Boundary |
|---|---|---|
| Open Core reference path | 8/8 conformance, 0/8 legacy differences | Bundled Pack and frozen frame fixtures only. |
| Structured assurance | 8/8 fixed cases; 0 false accepts/rejects | Declared schema, intent, and evidence signals only. |
| Candidate assurance | 11/11 fixed cases; 0 false accepts | Typed evidence/provenance policy only, not perception quality. |
| Grading assurance | 7/7 fixed cases; 0 false accepts | Rubric record audit only, not answer quality or fairness. |
| Acceptance challenge | 6/6 fixed cases; 0 false clears | Declared challenge/evidence signals only. |
| Quality discovery | 42 fixed cases: 39 PASS, 3 safe limits, 0 unexpected failures | Fixed cross-family regression only; no blind generalization. |
| Foundation knowledge pack | 52 low-risk authored facts; 20 bilingual fixed checks | Pattern retrieval only; not open-domain knowledge. |
| Gemma 4 E4B reference integration | Same-candidate demo records `lm_only` and `lm_with_lce` under a versioned profile | Structured-output integration only; no chat or factuality claim. |

## Capability Maturity

| Capability | State |
|---|---|
| Data-only local Pack/Profile loading and hash lock | Experimental GO |
| Trace/replay and bounded conversation state | Bounded GO |
| Structured-output gateway and declared assurance policy | Bounded GO |
| Candidate, grading, and acceptance assurance gates | Bounded GO |
| Optional local-model candidate adapter and Gemma 4 E4B reference profile | Bounded GO |
| Local HTTP Control API | Bounded GO; caller-owned model/tool execution and local-only security boundary. |
| Foundation knowledge JSONL pack | Bounded GO |
| MySQL Pack repository | Pending |
| Detached Pack signatures and key lifecycle | NO-GO |
| Independent holdout contract | Plan GO; metadata-only public manifest and custody rules are verified. |
| Independent blind/sealed generalization | NO-GO; evaluator-held corpus and first run are pending. |
| General chat, factuality, and 20B-class quality | Unmeasured; NO CLAIM |
| Automatic third-party plugins, autonomous tools, public service | NO-GO |
| Raspberry Pi production operation | NO-GO |

## Public Alpha Position

The local release candidate is **v0.1.0-alpha: Experimental Open Core +
Reference Pack + Reference Assurance Gateway**. A source ZIP, SHA-256, and
clean-checkout verification have been produced locally. The remaining external
publication action is creating the public GitHub repository named `LCE` under
the selected account and uploading the candidate tag and artifacts. Independent
evaluation remains required before any comparative-uplift claim, not before
this bounded alpha scope. The source-available license and Organization
approval boundary are documented in `LICENSE` and
`ORGANIZATIONAL_USE.md`. See [RELEASE_READINESS.md](RELEASE_READINESS.md).

## Source of Truth Rules

- Use this document for current counts and current release assertions.
- Use [EVALUATION_POLICY.md](EVALUATION_POLICY.md) before interpreting a score.
- Use [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md) to find current public
  documents and historical reports.
