# Security Policy

## Scope

LCE is experimental software. Network adapters, automatic third-party Pack
download, public service operation, and arbitrary plugins are not supported
release surfaces at this time.

## Report a Vulnerability

Do not disclose suspected vulnerabilities in public issues. Use the maintainer
contact form at <https://utakataservice.com/contact/contact.php> and state that
the report is security-sensitive. Do not include credentials or production
secrets. Until a report has been handled, do not deploy LCE on untrusted
networks or with production credentials.

## Security Boundaries

- Core validation, authorization, state bounds, trace integrity, and redaction
  are fail-closed contracts.
- Packs are data, not executable plugins.
- External tools require adapter-specific authorization and validation.
- Model content safety is delegated to the selected model; LCE focuses on
  structural and execution integrity.

Security documentation is not a guarantee that every adapter or Pack is safe.
Each public release must state its tested adapters and known exclusions.
