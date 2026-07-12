"""Call the local LCE Control API with a simulated LLM JSON candidate."""
from __future__ import annotations

import argparse
import json
from urllib.request import Request, urlopen


def post_json(base_url: str, path: str, value: dict) -> dict:
    request = Request(
        base_url.rstrip("/") + path,
        data=json.dumps(value, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8789")
    args = parser.parse_args()
    result = post_json(args.base_url, "/v1/gate/structured-output", {
        "raw_output": json.dumps({"summary": "More evidence is needed before changing the budget.", "certainty": "uncertain", "evidence_refs": []}),
        "contract": {
            "contract_id": "budget-summary-v1",
            "schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "certainty": {"type": "string", "enum": ["known", "uncertain"]},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["summary", "certainty", "evidence_refs"],
                "additionalProperties": False,
            },
        },
        "user_request": "Summarize the budget state.",
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
