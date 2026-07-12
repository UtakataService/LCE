# LCE Control API

The API is a local, JSON-only boundary for using LCE between your application
and an LLM, retrieval system, program, or other candidate producer.

```text
application -> LLM/tool/program -> LCE Control API -> application decision
```

The API does not call an LLM or execute a tool. The caller owns generation,
repair retries, authorization to act, and state commit.

## Start

```sh
python -m lce_validation.api_server --host 127.0.0.1 --port 8789
python examples/api_client_demo.py --base-url http://127.0.0.1:8789
```

Bind to loopback by default. Put authentication and a reverse proxy in front of
the API before exposing it beyond a trusted local environment.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Health and API version. |
| `GET` | `/v1/capabilities` | Gates and ownership boundaries. |
| `GET` | `/v1/openapi.json` | Compact OpenAPI discovery document. |
| `POST` | `/v1/gate/structured-output` | Validate raw JSON from an LLM or program. |
| `POST` | `/v1/gate/candidate` | Assess a typed candidate against evidence and action policy. |
| `POST` | `/v1/gate/acceptance-challenge` | Pause an accepted result when challenge signals require review. |

## Structured-output Flow

`POST /v1/gate/structured-output` takes `raw_output`, a LCE contract, and
optional declared assurance/evidence fields. Its response has one of these
decisions:

- `ACCEPT`: return `result.value` to the caller.
- `RETURN_TO_MODEL`: pass the returned repair instruction to the model, then
  submit the next candidate again.
- `HOLD`: do not act; obtain evidence or resolve the declared policy issue.

Example request:

```json
{
  "raw_output": "{\"summary\":\"Need more evidence.\",\"certainty\":\"uncertain\",\"evidence_refs\":[]}",
  "contract": {
    "contract_id": "summary-v1",
    "schema": {
      "type": "object",
      "properties": {
        "summary": {"type": "string"},
        "certainty": {"type": "string", "enum": ["known", "uncertain"]},
        "evidence_refs": {"type": "array", "items": {"type": "string"}}
      },
      "required": ["summary", "certainty", "evidence_refs"],
      "additionalProperties": false
    }
  }
}
```

## Security Boundary

This first API has no authentication, rate limit, or multi-tenant isolation.
It is a local integration API, not a public network service. Do not bind it to
an untrusted interface without adding those controls outside the current
reference implementation.
