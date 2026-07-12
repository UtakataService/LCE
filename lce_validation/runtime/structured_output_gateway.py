"""Model-agnostic structured-output boundary owned by LCE.

This deliberately supports a small, inspectable JSON-schema subset. It is a
contract gate, not a general JSON Schema implementation and never commits
model output to conversation state by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import json
import re
from typing import Any, Callable, Mapping


class StructuredOutputContractError(ValueError):
    pass


RepairFunction = Callable[[str], str]
_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
_FENCED_JSON = re.compile(r"\A\s*```(?:json)?\s*(.*?)\s*```\s*\Z", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True, slots=True)
class StructuredOutputContract:
    contract_id: str
    schema: dict[str, Any]
    defaults: dict[str, Any] | None = None
    max_repairs: int = 1
    allow_fenced_json: bool = True
    max_output_chars: int = 12000

    def as_prompt_contract(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "schema": self.schema,
            "defaults_applied_by_lce": sorted((self.defaults or {}).keys()),
            "output_rule": "Return exactly one JSON value. Do not add prose or markdown unless fenced JSON is explicitly permitted.",
        }


def build_structured_output_instruction(
    user_request: str,
    contract: StructuredOutputContract,
    *,
    context_summary: str = "",
    evidence_summary: str = "",
) -> str:
    """Build an instruction suitable even for an LLM without native JSON mode."""
    _validate_contract(contract)
    if not isinstance(user_request, str):
        raise StructuredOutputContractError("INVALID_USER_REQUEST")
    _validate_assurance_summary(context_summary, "INVALID_CONTEXT_SUMMARY")
    _validate_assurance_summary(evidence_summary, "INVALID_EVIDENCE_SUMMARY")
    context = f"LCE_CONTEXT_SUMMARY={context_summary}\n" if context_summary else ""
    evidence = f"LCE_EVIDENCE_SUMMARY={evidence_summary}\n" if evidence_summary else ""
    return (
        "Produce the requested result as exactly one JSON value that satisfies the LCE contract. "
        "Do not add explanation, headings, markdown, or unrequested keys. "
        "Do not invent values for unknown required fields; use the requested uncertainty field when the schema provides one.\n"
        f"LCE_CONTRACT={json.dumps(contract.as_prompt_contract(), ensure_ascii=False, sort_keys=True)}\n{context}{evidence}"
        f"USER_REQUEST={user_request}"
    )


def process_structured_output(
    raw_output: str,
    contract: StructuredOutputContract,
    *,
    repair_fn: RepairFunction | None = None,
    user_request: str = "",
    repair_context_summary: str = "",
    repair_evidence_summary: str = "",
) -> dict[str, Any]:
    """Parse, validate, safely default, and optionally repair one model output.

    No default may fill a required key, and a failed repair never exposes a
    partially valid value as accepted output.
    """
    _validate_contract(contract)
    parsed, parse_errors = _parse_output(raw_output, contract)
    value, violations = _validated_value(parsed, contract, parse_errors)
    attempts = 0
    if not violations:
        return _result("ACCEPTED", value, violations, attempts, raw_output, contract)

    repair_instruction = build_repair_instruction(
        user_request,
        raw_output,
        contract,
        violations,
        context_summary=repair_context_summary,
        evidence_summary=repair_evidence_summary,
    )
    if repair_fn is None or contract.max_repairs == 0:
        return _result("RETRY_REQUIRED", None, violations, attempts, raw_output, contract, repair_instruction)

    attempts = 1
    repaired_raw = repair_fn(repair_instruction)
    parsed, parse_errors = _parse_output(repaired_raw, contract)
    value, repair_violations = _validated_value(parsed, contract, parse_errors)
    if not repair_violations:
        return _result("REPAIRED", value, [], attempts, repaired_raw, contract)
    return _result("REJECTED", None, repair_violations, attempts, repaired_raw, contract, repair_instruction)


def build_repair_instruction(
    user_request: str,
    previous_output: str,
    contract: StructuredOutputContract,
    violations: list[str],
    *,
    context_summary: str = "",
    evidence_summary: str = "",
) -> str:
    """Create a bounded retry request. This string is never placed in the trace."""
    _validate_assurance_summary(context_summary, "INVALID_CONTEXT_SUMMARY")
    _validate_assurance_summary(evidence_summary, "INVALID_EVIDENCE_SUMMARY")
    context = f"LCE_CONTEXT_SUMMARY={context_summary}\n" if context_summary else ""
    evidence = f"LCE_EVIDENCE_SUMMARY={evidence_summary}\n" if evidence_summary else ""
    return (
        "Your previous output failed the LCE structured-output contract. Return a corrected JSON value only. "
        "Do not explain the correction and do not add keys.\n"
        f"LCE_CONTRACT={json.dumps(contract.as_prompt_contract(), ensure_ascii=False, sort_keys=True)}\n{context}{evidence}"
        f"VIOLATIONS={json.dumps(sorted(set(violations)))}\n"
        f"USER_REQUEST={user_request}\n"
        f"PREVIOUS_OUTPUT={previous_output}"
    )


def _validated_value(
    parsed: Any, contract: StructuredOutputContract, parse_errors: list[str]
) -> tuple[Any | None, list[str]]:
    if parse_errors:
        return None, parse_errors
    value = _apply_safe_defaults(parsed, contract)
    violations = _validate_schema(value, contract.schema)
    return value, violations


def _parse_output(raw_output: str, contract: StructuredOutputContract) -> tuple[Any | None, list[str]]:
    if not isinstance(raw_output, str) or not raw_output.strip():
        return None, ["EMPTY_OUTPUT"]
    if len(raw_output) > contract.max_output_chars:
        return None, ["MAX_OUTPUT_CHARS_EXCEEDED"]
    payload = raw_output.strip()
    match = _FENCED_JSON.fullmatch(payload)
    if match:
        if not contract.allow_fenced_json:
            return None, ["MARKDOWN_FENCE_NOT_ALLOWED"]
        payload = match.group(1).strip()
    try:
        return json.loads(payload), []
    except json.JSONDecodeError:
        return None, ["INVALID_JSON_OUTPUT"]


def _apply_safe_defaults(value: Any, contract: StructuredOutputContract) -> Any:
    if not isinstance(value, Mapping) or not contract.defaults:
        return value
    completed = copy.deepcopy(dict(value))
    required = set(contract.schema.get("required", []))
    properties = contract.schema.get("properties", {})
    for key, default in contract.defaults.items():
        if key in completed or key in required or key not in properties:
            continue
        if _validate_schema(default, properties[key], path=key):
            continue
        completed[key] = copy.deepcopy(default)
    return completed


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    expected = schema["type"]
    if not _matches_type(value, expected):
        return [f"{path}:EXPECTED_{expected.upper()}"]
    errors: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}:VALUE_NOT_IN_ENUM")
    if expected == "object":
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        for key in sorted(required - set(value)):
            errors.append(f"{path}.{key}:REQUIRED_PROPERTY_MISSING")
        if schema.get("additionalProperties", True) is False:
            for key in sorted(set(value) - set(properties)):
                errors.append(f"{path}.{key}:UNDECLARED_PROPERTY")
        for key, child in properties.items():
            if key in value:
                errors.extend(_validate_schema(value[key], child, f"{path}.{key}"))
    elif expected == "array":
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}:MIN_ITEMS_NOT_MET")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}:MAX_ITEMS_EXCEEDED")
        if "items" in schema:
            for index, child in enumerate(value):
                errors.extend(_validate_schema(child, schema["items"], f"{path}[{index}]"))
    elif expected == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}:MIN_LENGTH_NOT_MET")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}:MAX_LENGTH_EXCEEDED")
    return sorted(set(errors))


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object": return isinstance(value, Mapping)
    if expected == "array": return isinstance(value, list)
    if expected == "string": return isinstance(value, str)
    if expected == "number": return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer": return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean": return isinstance(value, bool)
    return value is None


def _validate_contract(contract: StructuredOutputContract) -> None:
    if not isinstance(contract, StructuredOutputContract) or not isinstance(contract.contract_id, str) or not contract.contract_id:
        raise StructuredOutputContractError("INVALID_STRUCTURED_OUTPUT_CONTRACT")
    if not isinstance(contract.schema, Mapping):
        raise StructuredOutputContractError("INVALID_OUTPUT_SCHEMA")
    _validate_schema_definition(contract.schema)
    if not isinstance(contract.defaults, (dict, type(None))):
        raise StructuredOutputContractError("INVALID_OUTPUT_DEFAULTS")
    if not isinstance(contract.max_repairs, int) or not 0 <= contract.max_repairs <= 2:
        raise StructuredOutputContractError("INVALID_REPAIR_LIMIT")
    if not isinstance(contract.max_output_chars, int) or not 1 <= contract.max_output_chars <= 12000:
        raise StructuredOutputContractError("INVALID_OUTPUT_SIZE_LIMIT")


def _validate_assurance_summary(value: str, error: str) -> None:
    if not isinstance(value, str) or len(value) > 4000:
        raise StructuredOutputContractError(error)


def _validate_schema_definition(schema: Mapping[str, Any]) -> None:
    kind = schema.get("type")
    if kind not in _TYPES:
        raise StructuredOutputContractError("UNSUPPORTED_SCHEMA_TYPE")
    if kind == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping) or not isinstance(schema.get("required", []), list):
            raise StructuredOutputContractError("INVALID_OBJECT_SCHEMA")
        if not set(schema.get("required", [])).issubset(properties):
            raise StructuredOutputContractError("REQUIRED_PROPERTY_NOT_DECLARED")
        for child in properties.values():
            if not isinstance(child, Mapping):
                raise StructuredOutputContractError("INVALID_PROPERTY_SCHEMA")
            _validate_schema_definition(child)
    if kind == "array" and "items" in schema:
        if not isinstance(schema["items"], Mapping):
            raise StructuredOutputContractError("INVALID_ARRAY_ITEM_SCHEMA")
        _validate_schema_definition(schema["items"])


def _result(
    status: str,
    value: Any | None,
    violations: list[str],
    attempts: int,
    raw_output: str,
    contract: StructuredOutputContract,
    repair_instruction: str | None = None,
) -> dict[str, Any]:
    result = {
        "status": status,
        "accepted": status in {"ACCEPTED", "REPAIRED"},
        "value": value,
        "violations": sorted(set(violations)),
        "repair_attempts": attempts,
        "trace": {
            "contract_id": contract.contract_id,
            "output_hash": "sha256:" + hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
            "status": status,
        },
        "claim_boundary": "Structured-format validation only; accepted JSON does not prove factual correctness, safety, policy compliance, or authorization to commit state.",
    }
    if repair_instruction is not None:
        result["repair_instruction"] = repair_instruction
    return result
