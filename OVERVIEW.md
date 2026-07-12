# LCE Overview

Last verified: 2026-07-12. This document describes the public-alpha target,
not every historical experiment in the repository.

## Product Boundary

LCE is an experimental CPU-first control runtime. It makes selected decisions
explicit and replayable around optional models and adapters:

```text
input + bounded context
  -> profile and Pack resolution
  -> route, evidence, authorization, and output contract
  -> optional LLM / retrieval / tool candidate
  -> structure, declared-policy, state, and trace checks
  -> accepted result, hold, rejection, or clarification
```

The generator is interchangeable. LCE owns the decision boundary for the
contracts it has been configured to enforce; it does not infer unconfigured
truth, intent, or safety properties.

## Core and Data Boundaries

| Layer | Owns | Does not own |
|---|---|---|
| Core | schema, state bounds, trace/replay, profile locking, declared policy checks | free-form language generation or general truth |
| Pack/Profile | language labels, semantic mappings, reference data, model profiles, control rules | executable code that bypasses Core invariants |
| Adapter | candidate generation or retrieval from a selected external system | authorization, direct state commit, final acceptance |
| Evidence catalog | declared references and their support/contradiction status | automatic real-world verification |

Core invariants are fail-closed where an adapter lacks required structure,
authorization, or declared evidence. Model content moderation is deliberately
model-owned; LCE does not duplicate a general content safety classifier.

## Current Public Alpha Surface

1. **Open Core SDK**: local JSON Pack resolution, profile hash locking,
   language-Pack conformance, and frozen shadow comparison.
2. **Assurance gates**: structured JSON, candidate, grading, and acceptance
   challenge decisions over declared inputs.
3. **Reference applications**: dependency-free Open Core and assurance-gateway
   examples.
4. **Optional Ollama adapter**: model output remains a candidate until it
   clears the selected LCE contract.

The detailed component inventory is in [CORE_COMPONENTS.md](CORE_COMPONENTS.md).

## Evidence and Non-Claims

Current regression evidence is deliberately bounded. Fixed fixtures show that
implemented contracts continue to behave as specified; they do not establish
generalization. The current public snapshot, including test command and counts,
is [CURRENT_STATUS.md](CURRENT_STATUS.md).

The live Gemma E4B experiment demonstrates an integration property: LCE can
reject certain evidence-contract failures after an 8.0B local model produces
valid JSON. It does not establish model intelligence, factual correctness,
natural conversation quality, or a parameter-equivalent uplift.

## Explicit No-Go Areas

- General LLM equivalence or standalone 20B-class quality.
- Blind/sealed generalization claims.
- Third-party Pack distribution or plugin execution.
- Autonomous external actions and public service operation.
- Production Raspberry Pi deployment.

## Public Alpha Decision

The release candidate is **Experimental Open Core + Reference Pack + Reference
Assurance Gateway**. Its current gates and outstanding blockers are maintained
in [RELEASE_READINESS.md](RELEASE_READINESS.md). Historical design and research
reports remain in `outputs/` and are indexed by [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md).
