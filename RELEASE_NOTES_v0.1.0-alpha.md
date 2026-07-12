# LCE v0.1.0-alpha

**Experimental Open Core + Reference Pack + Reference Assurance Gateway**

## What Is Included

- Data-only LCE Core contracts, reference Pack/Profile loading, trace/replay,
  structured-output validation, candidate assurance, grading assurance, and
  acceptance challenge gates.
- A local, JSON-only HTTP Control API. The application owns model/tool calls,
  retries, authorization, and state commits.
- Dependency-free Open Core and Reference Assurance Gateway examples.
- A reproducible local Ollama `gemma4:e4b` reference integration that compares
  the same raw model candidate with and without the declared LCE assurance
  policy.
- Public regression fixtures, metadata-only independent-holdout plan, CI, and
  source-tree privacy checks.

## Verified Reference Evidence

```text
python -m pytest -q
548 passed, 4 skipped, 72 subtests passed
```

The four skipped tests are service-dependent lanes and are not successes.
Use [CURRENT_STATUS.md](CURRENT_STATUS.md) and
[EVALUATION_POLICY.md](EVALUATION_POLICY.md) before interpreting any result.

## Known Limits

- This is not an LLM and does not claim 20B-class chat quality, open-domain
  factuality, general safety, or generalization from fixed fixtures.
- The Gemma reference is a local structured-output integration probe, not a
  chat or factuality benchmark.
- No public-network API, autonomous tool execution, third-party Pack download,
  Pack signature lifecycle, or arbitrary plugin execution is provided.
- Independent evaluator-held and blind/sealed runs are not complete.
- Organizational use requires prior written permission under `LICENSE`.

## Support and Security

For reproducible bugs, feature proposals, organizational-use requests, or a
private security report, use the maintainer contact form:

<https://utakataservice.com/contact/contact.php>

Do not submit credentials, production secrets, or sensitive customer data.
