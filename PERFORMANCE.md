# Performance Scope

LCE performance evidence is separated into Core-only and model-assisted paths.
They must not be combined into a token-per-second claim.

## Core-only Reference Lane

`run-reference-performance` measures repeated execution of:

```text
profile lock + 8-case conformance + 8-case shadow ledger
```

The latest saved Windows reference run used 30 repetitions and observed a mean
of 37.66 ms, p50 37.63 ms, p95 40.33 ms, and 368,443 bytes peak `tracemalloc`
allocation. It is a small local regression budget, not chat, capacity, GPU,
network, or Raspberry Pi evidence.

```powershell
python -m lce_validation.cli run-reference-performance --out reference-performance --repeats 50
```

## Gemma E4B-assisted Lane

The 2026-07-12 structured-output probe observed warmed single requests around
0.72--1.17 seconds. The model generation dominated the path; the LCE gate did
not add a separately measured material delay in that small probe. The first
model request took about 7.5 seconds to warm up.

This is six live contract cases for one local model/profile, not a throughput,
chat, factuality, or capacity benchmark.

## Required Future Measurements

Before claiming target-environment support, publish CPU/RAM/p50/p95 and Pack
size for each of: Windows CPU Core-only, Raspberry Pi Core-only, and each
declared local-model profile. Include cold and warm runs, concurrency, trace
storage, and external-call counts.
