# Reference Assurance Gateway

`examples/reference_assurance_gateway.py` is the public-alpha reference
application. It is intentionally small, deterministic, and dependency-free.

It demonstrates three decisions:

1. An evidence-backed display-only candidate is accepted.
2. The same candidate is held when it requests a state-changing scope without
   authorization.
3. An accepted result is blocked from promotion after a required cross-check
   fails.

```powershell
py -3.11 examples\reference_assurance_gateway.py
```

The reference application does not call a model, execute a tool, or establish
the truth of candidate content. It makes the LCE decision boundary inspectable.

## Control API

`lce_validation.api_server` exposes the same boundary over local HTTP so an
application can call an LLM, RAG system, or program and submit its candidate to
LCE before returning it or acting on it. See [API.md](API.md) and
`examples/api_client_demo.py`.

The API is the reference integration surface. A versioned live Gemma E4B
profile/demo remains a separate release task; current live evidence is in
`outputs/gemma4-e4b-lce-ablation-20260712/`.
