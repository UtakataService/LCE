"""Bounded structured-output instruction recognition, generation, and validation."""
from __future__ import annotations

import json
import math
import re
from enum import Enum
from typing import Any, Mapping


class Intent(str, Enum):
    YES = "YES"
    NO = "NO"
    AMBIGUOUS = "AMBIGUOUS"


class StructuredIOError(ValueError):
    pass


SUPPORTED_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}
MAX_DEPTH = 6
MAX_PROPERTIES = 64
MAX_ARRAY_ITEMS = 100


def recognize_structured_request(instruction: str, schema: Any = None) -> Intent:
    text = instruction.casefold()
    explicit_refusal = ("jsonでは返さない", "jsonにしない", "構造化しない", "do not return json", "don't return json")
    if any(token in text for token in explicit_refusal):
        return Intent.NO
    if schema is not None:
        return Intent.YES
    negative = ("jsonとは", "jsonについて説明", "構造化出力とは", "what is json", "explain json")
    strong = ("jsonで", "json形式", "json object", "structured output", "構造化出力", "次のスキーマ", "schemaに")
    if any(token in text for token in negative):
        return Intent.NO
    if any(token in text for token in strong):
        return Intent.YES
    if ("項目" in text or "fields" in text) and any(token in text for token in ("出力", "返して", "まとめて", "output", "return")):
        return Intent.AMBIGUOUS
    return Intent.NO


def _strict_json_loads(value: str) -> Any:
    def reject_constant(token: str) -> None:
        raise StructuredIOError(f"NON_FINITE_NUMBER:{token}")
    return json.loads(value, parse_constant=reject_constant)


def parse_schema(schema: Any, instruction: str = "") -> dict[str, Any]:
    if schema is None:
        blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", instruction, re.S | re.I)
        if not blocks:
            raise StructuredIOError("SCHEMA_REQUIRED")
        schema = _strict_json_loads(blocks[-1])
    elif isinstance(schema, str):
        schema = _strict_json_loads(schema)
    if not isinstance(schema, dict):
        raise StructuredIOError("SCHEMA_MUST_BE_OBJECT")
    _check_schema(schema, 0)
    return schema


def _same_json_type(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right)
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return True
    return type(left) is type(right)


def _value_has_type(value: Any, typ: str) -> bool:
    checks = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
    }
    return checks[typ](value)


def _check_schema(schema: Mapping[str, Any], depth: int) -> None:
    if depth > MAX_DEPTH:
        raise StructuredIOError("SCHEMA_TOO_DEEP")
    allowed = {"type", "properties", "required", "additionalProperties", "items", "enum", "minItems", "maxItems"}
    unknown = set(schema) - allowed
    if unknown:
        raise StructuredIOError("UNSUPPORTED_SCHEMA_KEY:" + ",".join(sorted(unknown)))
    typ = schema.get("type")
    if typ not in SUPPORTED_TYPES:
        raise StructuredIOError("UNSUPPORTED_TYPE")
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list) or not enum:
            raise StructuredIOError("INVALID_ENUM")
        if any(not _value_has_type(item, typ) for item in enum):
            raise StructuredIOError("ENUM_TYPE_MISMATCH")
        if any(_same_json_type(a, b) and a == b for i, a in enumerate(enum) for b in enum[i + 1 :]):
            raise StructuredIOError("DUPLICATE_ENUM")
    if typ == "object":
        if "properties" not in schema or "additionalProperties" not in schema:
            raise StructuredIOError("CLOSED_OBJECT_SCHEMA_REQUIRED")
        props = schema["properties"]
        if not isinstance(props, dict) or len(props) > MAX_PROPERTIES:
            raise StructuredIOError("INVALID_PROPERTIES")
        required = schema.get("required", [])
        if (not isinstance(required, list) or len(required) != len(set(required))
                or not all(isinstance(key, str) and key in props for key in required)):
            raise StructuredIOError("INVALID_REQUIRED")
        if schema["additionalProperties"] is not False:
            raise StructuredIOError("ADDITIONAL_PROPERTIES_MUST_BE_FALSE")
        for child in props.values():
            if not isinstance(child, dict):
                raise StructuredIOError("INVALID_PROPERTY_SCHEMA")
            _check_schema(child, depth + 1)
    elif typ == "array":
        if not isinstance(schema.get("items"), dict):
            raise StructuredIOError("ARRAY_ITEMS_REQUIRED")
        minimum, maximum = schema.get("minItems", 0), schema.get("maxItems", MAX_ARRAY_ITEMS)
        if (not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0
                or not isinstance(maximum, int) or isinstance(maximum, bool)
                or maximum < minimum or maximum > MAX_ARRAY_ITEMS):
            raise StructuredIOError("INVALID_ARRAY_LIMITS")
        _check_schema(schema["items"], depth + 1)
    elif any(key in schema for key in ("properties", "required", "additionalProperties", "items", "minItems", "maxItems")):
        raise StructuredIOError("TYPE_SPECIFIC_KEYWORD_MISMATCH")


def validate(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    typ = schema["type"]
    if not _value_has_type(value, typ):
        return [f"{path}:TYPE_{typ.upper()}_REQUIRED"]
    errors: list[str] = []
    if "enum" in schema and not any(_same_json_type(value, item) and value == item for item in schema["enum"]):
        errors.append(f"{path}:ENUM_VIOLATION")
    if typ == "object":
        props = schema["properties"]
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}:REQUIRED")
        for key, item in value.items():
            if key not in props:
                errors.append(f"{path}.{key}:ADDITIONAL_PROPERTY")
            else:
                errors.extend(validate(item, props[key], f"{path}.{key}"))
    elif typ == "array":
        if len(value) > schema.get("maxItems", MAX_ARRAY_ITEMS):
            errors.append(f"{path}:MAX_ITEMS")
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}:MIN_ITEMS")
        for index, item in enumerate(value):
            errors.extend(validate(item, schema["items"], f"{path}[{index}]"))
    return errors


def _coerce(value: Any, typ: str) -> Any:
    if typ == "string" and isinstance(value, str):
        return value
    if typ == "integer" and isinstance(value, str) and re.fullmatch(r"-?(?:0|[1-9]\d*)", value.strip()):
        return int(value)
    if typ == "number" and isinstance(value, str) and re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?", value.strip()):
        return float(value)
    if typ == "boolean" and isinstance(value, str) and value.casefold() in {"true", "false", "はい", "いいえ"}:
        return value.casefold() in {"true", "はい"}
    return value


def generate(data: Any, schema: Mapping[str, Any]) -> Any:
    typ = schema["type"]
    if typ == "object":
        if not isinstance(data, Mapping):
            raise StructuredIOError("INPUT_OBJECT_REQUIRED")
        return {key: generate(data[key], child) for key, child in schema["properties"].items() if key in data}
    if typ == "array":
        if not isinstance(data, list):
            raise StructuredIOError("INPUT_ARRAY_REQUIRED")
        if len(data) > schema.get("maxItems", MAX_ARRAY_ITEMS):
            raise StructuredIOError("INPUT_ARRAY_TOO_LARGE")
        return [generate(item, schema["items"]) for item in data]
    return _coerce(data, typ)


def run_structured_io(*, instruction: str, data: Any, schema: Any = None) -> dict[str, Any]:
    intent = recognize_structured_request(instruction, schema)
    if intent is Intent.NO:
        return {"ok": False, "route": "normal_dialogue", "intent": intent.value, "errors": ["NOT_STRUCTURED_REQUEST"]}
    if intent is Intent.AMBIGUOUS:
        return {"ok": False, "route": "structured_clarification", "intent": intent.value, "errors": ["STRUCTURE_INSTRUCTION_AMBIGUOUS"]}
    try:
        contract = parse_schema(schema, instruction)
        output = generate(data, contract)
        serialized = json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        reparsed = _strict_json_loads(serialized)
        errors = validate(reparsed, contract)
    except (StructuredIOError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {"ok": False, "route": "structured_rejected", "intent": intent.value, "errors": [str(exc)]}
    return {
        "ok": not errors,
        "route": "structured_output" if not errors else "structured_rejected",
        "intent": intent.value,
        "format": "json",
        "schema": contract,
        "structured_output": reparsed if not errors else None,
        "response": serialized if not errors else "",
        "errors": errors,
        "claim": "bounded_json_schema_subset",
    }
