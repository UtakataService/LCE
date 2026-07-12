# LCE: Lightweight Cognitive Engine

> A CPU-first decision and assurance layer for LLMs, retrieval, APIs, and rule-based systems.

[日本語](README_JA.md) | [Quickstart](QUICKSTART.md) | [Install with pip](PIP_INSTALL.md) | [API](API.md) | [Current status](CURRENT_STATUS.md)

![LCE decision core architecture](assets/lce-decision-core.png)

## What LCE Is

LCE is not a language model and does not try to replace a transformer. It is a
small, inspectable control layer that evaluates a candidate produced by an LLM,
search system, business API, sensor, or rule engine before the surrounding
application decides what to do next.

A fluent answer or syntactically valid JSON is not automatically authorized,
grounded in declared evidence, compatible with a state transition, or safe to
commit to an external system. LCE makes those checks explicit and returns a
bounded decision.

```text
input
  -> application selects a model, search, API, or rule producer
  -> producer returns a candidate
  -> LCE validates declared contracts, evidence, authorization, and state bounds
  -> ACCEPT / RETURN_TO_MODEL / HOLD or a typed assurance decision
  -> application owns retry, external execution, and state commit
```

LCE never silently takes over model generation, tool execution, authorization,
or database writes. Those actions remain caller-owned by design.

## Why Put LCE Between a Model and an Action?

Without a control layer, an application accumulates prompt-specific conditionals
around each model call: choose a model, decide whether retrieval is needed,
verify JSON, reject unsupported evidence, limit an action, and remember why a
result was accepted. LCE centralizes the bounded parts of that path into
versioned data contracts and traceable gates.

Use it when the important question is not only "can a model answer this?" but
also:

- Does the output satisfy the JSON contract expected by the next component?
- Is a `known` claim backed by declared evidence references?
- Is the candidate allowed to affect the requested action scope?
- Does a required cross-check contradict a previously accepted result?
- Can a reviewer replay why the application accepted, held, or returned it?

## What the Core Does

| Surface | LCE responsibility | Boundary |
|---|---|---|
| Structured output | Parse JSON, validate an inspectable schema subset, apply safe defaults, and return repair instructions. | Valid JSON is not proof of truth or usefulness. |
| Declared assurance | Check required values, terms, evidence references, certainty rules, and forbidden terms from policy. | No general intent or real-world truth inference. |
| Candidate assurance | Check typed candidates against declared provenance, confidence, authorization, and action scope. | LCE does not execute the candidate. |
| Acceptance challenge | Re-open an accepted result when required cross-checks or evidence signals fail. | It does not replace human review. |
| State and trace | Bound state updates and produce deterministic trace/replay evidence. | It is not open-ended memory. |
| Pack and profile loading | Load data-only language, policy, and model profiles with content-hash locking. | Packs cannot install executable bypass hooks. |

## A Typical Integration

The local HTTP Control API is intentionally small. Your application calls the
producer, sends its raw candidate to LCE, and then acts only on the returned
decision.

```text
application -> local LLM / RAG / business API -> LCE Control API -> application
```

For structured output, send `raw_output` and a contract to
`POST /v1/gate/structured-output`.

- **ACCEPT**: use `result.value` as the validated candidate.
- **RETURN_TO_MODEL**: send LCE's bounded repair instruction back to the
  producer, then submit the next candidate.
- **HOLD**: do not act until the application obtains evidence or resolves the
  declared policy condition.

The API does not call an LLM, browse the web, execute a tool, or commit state.
That separation lets LCE work with local models, frontier-model APIs,
non-language services, and deterministic programs. See [API.md](API.md) for
request formats and ownership details.

## Install

Python 3.11 or later is required. The package is not on PyPI yet; install the
published alpha directly from GitHub:

```powershell
python -m pip install "lce-open-core @ git+https://github.com/UtakataService/LCE.git@v0.1.0-alpha.1"
```

This provides:

```powershell
lce --help
lce-api --host 127.0.0.1 --port 8789
python -m lce_validation --help
```

Release-wheel and editable installation are documented in
[PIP_INSTALL.md](PIP_INSTALL.md).

## Try the Reference Paths

The first two examples have no model or network dependency:

```powershell
python examples\quickstart_open_core.py
python examples\reference_assurance_gateway.py
```

Start the local API and send a sample candidate:

```powershell
python -m lce_validation.api_server --host 127.0.0.1 --port 8789
python examples\api_client_demo.py --base-url http://127.0.0.1:8789
```

An optional local Ollama reference uses `gemma4:e4b`. It generates one raw
candidate per case, then evaluates that exact candidate in `lm_only` and
`lm_with_lce` modes so a second generation cannot distort the comparison.

```powershell
python examples\gemma4_e4b_reference_demo.py --out gemma4-e4b-reference.json
```

The recorded tag used an 8.0B Q4_K_M model. This is a structured-output
integration probe, not a chat or factuality benchmark. See
[GEMMA4_E4B_REFERENCE.md](GEMMA4_E4B_REFERENCE.md).

## What LCE Does Not Claim

LCE is intentionally narrow. It does **not** claim general dialogue quality,
factual accuracy, 20B-class standalone ability, general safety moderation,
autonomous tool use, public-network hosting, arbitrary plugin execution, or
generalization from fixed regression fixtures.

Read [CURRENT_STATUS.md](CURRENT_STATUS.md) and
[EVALUATION_POLICY.md](EVALUATION_POLICY.md) before interpreting a result.

## Documentation and License

The public alpha is **Experimental Open Core + Reference Pack + Reference
Assurance Gateway**. It includes a local API, reproducible reference paths, a
versioned Gemma integration, a metadata-only independent-holdout plan, and
public regression evidence. It remains experimental.

- [Quickstart](QUICKSTART.md): examples and regression commands.
- [Overview](OVERVIEW.md): architecture, ownership boundaries, and non-claims.
- [Current status](CURRENT_STATUS.md): verified counts and remaining NO-GO areas.
- [Evaluation policy](EVALUATION_POLICY.md) and [holdout plan](EVALUATION_HOLDOUT_PLAN.md): evidence boundaries and evaluator custody.
- [Pack trust boundary](PACK_TRUST.md): why Packs are data rather than plugins.
- [Contributing](CONTRIBUTING.md), [Security](SECURITY.md), and [Support](SUPPORT.md).

LCE is source-available: individual users receive broad rights, while
organizational use requires prior written permission. It is not an
OSI-approved open-source license. See [LICENSE](LICENSE),
[LICENSE_POLICY.md](LICENSE_POLICY.md), and
[ORGANIZATIONAL_USE.md](ORGANIZATIONAL_USE.md).
