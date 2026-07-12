# Gemma 4 E4B Reference Integration

## Scope

This reference demonstrates a caller-owned local Ollama integration using
`gemma4:e4b` and the LCE structured-output and declared-evidence gates. It is
not a benchmark of general dialogue, factuality, safety, coding ability, or
model quality.

The local tag must not be interpreted as a parameter count. The release
reference run observed **8.0B** parameters with **Q4_K_M** quantization. Each
run records the full Ollama digest returned by `/api/tags`.

## Reproduce

Install and start Ollama, then obtain the model:

```powershell
ollama pull gemma4:e4b
ollama serve
```

From a repository checkout, run:

```powershell
python examples\gemma4_e4b_reference_demo.py --out gemma4-e4b-reference.json
```

The command writes a JSON evidence file containing the exact model digest,
parameter metadata, profile ID, raw-output hashes, `lm_only` structural result,
`lm_with_lce` result, violations, and per-case generation latency. It uses the
versioned data-only profile in
[`profiles/gemma4_e4b_reference_profile_v1.json`](profiles/gemma4_e4b_reference_profile_v1.json)
and three public English/Japanese demonstration cases.

## Comparison Semantics

For each case, the demo invokes the model once. The exact raw output is then
evaluated twice:

```text
lm_only       LCE structured schema validation only.
lm_with_lce   The same structural result plus declared certainty/evidence checks.
```

There is no second model call for `lm_with_lce`; this prevents a comparison
from being distorted by two different generated candidates. The profile sets
`temperature: 0` and `seed: 7`, but local inference remains an integration
run, not a deterministic proof across all Ollama versions and hardware.

## Expected Shape

The example includes a supported `known` statement, an `uncertain` statement
without evidence, and an intentional `known` statement without evidence. The
last one commonly remains schema-valid in `lm_only` but is held by the
declared LCE assurance policy. The result is still limited to the specific
contract and cases used in that execution.

The demonstration does not grant LCE ownership of model generation, retries,
tool execution, authorization, state commit, or content-safety refusal.

## Recorded Release Reference

The release-candidate execution used Ollama 0.30.10 with
`gemma4:e4b` digest
`c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb`.
It generated three schema-valid candidates; LCE accepted two and semantically
rejected one `known` response without the required declared evidence. The
result is a reproducible integration probe, not an independent holdout.
