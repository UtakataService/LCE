# Quickstart

## Requirements

- Python 3.11 or later
- A checkout of this repository

The two reference examples use only the Python standard library. They do not
download a model, call a network service, or mutate a database.

## 1. Open Core Reference Path

```powershell
py -3.11 examples\quickstart_open_core.py
```

Expected shape:

```text
profile_lock: sha256:...
conformance: 8 passed, 0 failed
shadow_ledger: 8 equal, 0 different
```

This locks the bundled Profile, resolves the exact Reference Pack, runs eight
conformance cases, and compares them with a frozen legacy frame path.

## 2. Reference Assurance Gateway

```powershell
py -3.11 examples\reference_assurance_gateway.py
```

Expected shape:

```text
candidate_accepted: ACCEPT
candidate_authorization_hold: HOLD
promotion_gate: BLOCK
```

This shows an evidence-backed candidate, a state-changing candidate held for
authorization, and an accepted result blocked by a failed cross-check.

## 3. Local Control API

In one terminal:

```powershell
python -m lce_validation.api_server --host 127.0.0.1 --port 8789
```

In another terminal:

```powershell
python examples\api_client_demo.py --base-url http://127.0.0.1:8789
```

The client sends a simulated model JSON candidate to LCE. Use the same API
shape after your own LLM, RAG, or program call. The API does not own model
execution, retries, authorization, or state commit.

## 4. Gemma 4 E4B Reference Integration

With local Ollama running and `gemma4:e4b` installed:

```powershell
python examples\gemma4_e4b_reference_demo.py --out gemma4-e4b-reference.json
```

This invokes the model once per case, then compares the same candidate with
schema-only validation and with the declared LCE evidence gate. See
[GEMMA4_E4B_REFERENCE.md](GEMMA4_E4B_REFERENCE.md) for its exact scope.

## 5. Full Regression

Install `pytest` in an isolated environment, then run:

```powershell
python -m pytest -q
python -m lce_validation.cli run-public-readiness-evidence --out public-readiness-evidence
```

The first command is the full regression suite. The second emits fixed
assurance evidence; neither command establishes general LLM quality or
production readiness.

## Limits

These examples do not demonstrate an LLM, open-domain dialogue, web retrieval,
third-party Packs, tool execution, or general safety. See
[CURRENT_STATUS.md](CURRENT_STATUS.md) and [RELEASE_READINESS.md](RELEASE_READINESS.md).
