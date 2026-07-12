# LCE: Lightweight Cognitive Engine

> Experimental Open Core for bounded judgement, verification, and control around language models and tools.

[日本語](README_JA.md) | [Overview](OVERVIEW.md) | [Quickstart](QUICKSTART.md) | [Release readiness](RELEASE_READINESS.md) | [Current status](CURRENT_STATUS.md)

LCE is not a language model and does not replace a transformer. It is a small,
inspectable control layer that can sit before and after an LLM, retrieval
system, or tool adapter.

```text
request -> LCE policy / evidence / contract -> optional model or tool
        -> LCE schema / authorization / state / trace gate -> result
```

## What Is Available

- Data-only Pack and Profile loading with content-hash locking.
- Deterministic trace/replay for bounded state transitions.
- Structured-output parsing, schema validation, bounded repair, and declared
  evidence/intent checks.
- Candidate, grading, and accepted-result assurance gates.
- A local HTTP Control API for placing LCE between your application and a
  model, retrieval system, or program.
- A small reference SDK and two dependency-free examples.

## What Is Not Claimed

- General chat quality, factual accuracy, or general reasoning parity with an LLM.
- 20B-class standalone quality.
- Third-party Pack distribution, arbitrary plugin execution, public service
  operation, or Raspberry Pi production readiness.

## Try It

Python 3.11+ is required. From the repository root:

```powershell
py -3.11 examples\quickstart_open_core.py
py -3.11 examples\reference_assurance_gateway.py
```

The examples use no model, network, or mutable persistence. See
[QUICKSTART.md](QUICKSTART.md) for expected output and verification.

## Install with pip

Install the alpha directly from GitHub:

```powershell
python -m pip install "lce-open-core @ git+https://github.com/UtakataService/LCE.git@v0.1.0-alpha.1"
```

This provides `lce`, `lce-api`, and `python -m lce_validation`. The package is
not yet published to PyPI. See [PIP_INSTALL.md](PIP_INSTALL.md) for the release
wheel path and the command boundary.

## Integrate Through the API

Start the local API, send an LLM or program candidate to a gate, and use the
returned decision before acting:

```powershell
python -m lce_validation.api_server --host 127.0.0.1 --port 8789
python examples\api_client_demo.py --base-url http://127.0.0.1:8789
```

The API returns `ACCEPT`, `RETURN_TO_MODEL`, or `HOLD`; it does not run the
model or tool itself. See [API.md](API.md).

## LLM Integration Evidence

LCE can receive a local model candidate through an adapter and retain the final
accept/reject decision. A live `gemma4:e4b` experiment used an 8.0B Q4_K_M
local model and showed that LCE can block declared evidence-contract failures
that are syntactically valid JSON. This is a narrow structured-output result,
not a chat-quality or factuality comparison.

See [the live ablation report](outputs/gemma4-e4b-lce-ablation-20260712/REPORT_JA.md).
The versioned, same-candidate reference demo is documented in
[GEMMA4_E4B_REFERENCE.md](GEMMA4_E4B_REFERENCE.md).

## Public Alpha Scope

The intended first public release is **v0.1.0-alpha: Experimental Open Core +
Reference Pack + Reference Assurance Gateway**. It will be released only after
the items in [RELEASE_READINESS.md](RELEASE_READINESS.md) are satisfied.

The repository uses a source-available license: Individual Users receive broad
rights, while Organizational use requires prior written permission. It is not
an OSI-approved open-source license. See [LICENSE](LICENSE),
[ORGANIZATIONAL_USE.md](ORGANIZATIONAL_USE.md), and
[LICENSE_POLICY.md](LICENSE_POLICY.md).

## Documentation

- [Documentation index](DOCUMENTATION_INDEX.md)
- [Architecture and boundaries](OVERVIEW.md)
- [Open Core SDK](OPEN_CORE_SDK.md)
- [pip installation](PIP_INSTALL.md)
- [Evaluation policy](EVALUATION_POLICY.md)
- [Independent holdout plan](EVALUATION_HOLDOUT_PLAN.md)
- [Gemma 4 E4B reference integration](GEMMA4_E4B_REFERENCE.md)
- [Pack trust boundary](PACK_TRUST.md)
- [Contributing](CONTRIBUTING.md) and [security](SECURITY.md)
