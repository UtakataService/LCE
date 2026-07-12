from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SchemaError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_required(row: dict[str, Any], required: list[str], *, label: str = "row") -> list[str]:
    errors: list[str] = []
    for field in required:
        if field not in row:
            errors.append(f"{label}: missing required field {field}")
        elif row[field] is None:
            errors.append(f"{label}: field {field} is null")
    return errors


def validate_enum(row: dict[str, Any], enums: dict[str, list[str]], *, label: str = "row") -> list[str]:
    errors: list[str] = []
    for field, allowed in enums.items():
        if field in row and row[field] not in allowed:
            errors.append(f"{label}: field {field} has invalid value {row[field]!r}; allowed={allowed}")
    return errors


def validate_row(row: dict[str, Any], schema: dict[str, Any], *, label: str = "row") -> list[str]:
    errors = validate_required(row, list(schema.get("required", [])), label=label)
    properties = schema.get("properties", {})
    enums: dict[str, list[str]] = {}
    for field, spec in properties.items():
        if "enum" in spec:
            enums[field] = list(spec["enum"])
    errors.extend(validate_enum(row, enums, label=label))
    return errors


def validate_jsonl(path: str | Path, schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{i}: invalid JSON: {exc}")
            continue
        errors.extend(validate_row(row, schema, label=f"{path}:{i}"))
    return errors


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
