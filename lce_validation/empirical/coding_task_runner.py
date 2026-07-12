from __future__ import annotations

import ast
import json
import textwrap
from pathlib import Path
from typing import Any

from .engine import load_jsonl
from .seeded_dialogue import stable_seed
from .topic_continuity_dialogue import respond_with_topic_continuity


SUPPORTED_TASKS = {
    "sum_numbers": {
        "function_name": "solve",
        "code": """
def solve(numbers):
    total = 0
    for number in numbers:
        total += number
    return total
""",
        "tests": [
            {"args": [[1, 2, 3]], "expected": 6},
            {"args": [[]], "expected": 0},
            {"args": [[-2, 5]], "expected": 3},
        ],
    },
    "reverse_string": {
        "function_name": "solve",
        "code": """
def solve(text):
    return text[::-1]
""",
        "tests": [
            {"args": ["abc"], "expected": "cba"},
            {"args": [""], "expected": ""},
            {"args": ["level"], "expected": "level"},
        ],
    },
    "count_vowels": {
        "function_name": "solve",
        "code": """
def solve(text):
    vowels = set("aeiouAEIOU")
    count = 0
    for char in text:
        if char in vowels:
            count += 1
    return count
""",
        "tests": [
            {"args": ["hello"], "expected": 2},
            {"args": ["xyz"], "expected": 0},
            {"args": ["AEIo"], "expected": 4},
        ],
    },
}


BLOCKED_PATTERNS = [
    "import os",
    "import subprocess",
    "open(",
    "eval(",
    "exec(",
    "__import__",
    "socket",
    "requests",
]


def run_coding_task(prompt: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    task = classify_coding_task(prompt)
    dialogue = respond_with_topic_continuity(prompt, history or [])
    if task["task_type"] == "unknown":
        return {
            "ok": True,
            "route": "coding_clarify",
            "prompt": prompt,
            "task": task,
            "dialogue_route": dialogue["route"],
            "response": "I can attempt only small pure-function tasks for now. Please ask for sum_numbers, reverse_string, or count_vowels.",
            "output_chunks": [
                {"chunk_id": "out-01", "role": "clarify", "seed": stable_seed(prompt, salt="lce-coding-clarify-v0"), "text": "Supported coding tasks are currently limited to small pure functions."}
            ],
            "code": "",
            "verification": {"ok": False, "reason": "unknown_supported_task"},
            "repair": {"needed": True, "hint": "Narrow the request to a supported pure function."},
            "claim": "bounded_coding_task_runner_only",
            "blocked_claims": blocked_claims(),
        }

    candidate = build_candidate(task)
    validation = validate_candidate(candidate["code"], candidate["function_name"])
    verification = verify_candidate(candidate) if validation["ok"] else validation
    repair = repair_hint(task, validation, verification)
    route = "coding_pass" if verification["ok"] else "coding_repair"
    return {
        "ok": True,
        "route": route,
        "prompt": prompt,
        "seed": stable_seed(prompt, salt="lce-coding-task-v0"),
        "task": task,
        "dialogue_route": dialogue["route"],
        "code": candidate["code"],
        "verification": verification,
        "repair": repair,
        "response": response_text(route, task, verification, repair),
        "output_chunks": coding_output_chunks(prompt, route, candidate, verification, repair),
        "claim": "bounded_coding_task_runner_only",
        "blocked_claims": blocked_claims(),
    }


def classify_coding_task(prompt: str) -> dict[str, Any]:
    lowered = prompt.lower()
    if any(word in lowered for word in ["sum", "add numbers", "total"]):
        task_type = "sum_numbers"
    elif any(word in lowered for word in ["reverse", "backwards"]):
        task_type = "reverse_string"
    elif any(word in lowered for word in ["vowel", "vowels"]):
        task_type = "count_vowels"
    else:
        task_type = "unknown"
    return {
        "task_type": task_type,
        "constraints": [
            "pure_function_only",
            "no_imports",
            "no_filesystem",
            "no_network",
            "deterministic_tests",
        ],
    }


def build_candidate(task: dict[str, Any]) -> dict[str, Any]:
    spec = SUPPORTED_TASKS[task["task_type"]]
    code = textwrap.dedent(spec["code"]).strip() + "\n"
    return {
        "task_type": task["task_type"],
        "function_name": spec["function_name"],
        "code": code,
        "tests": spec["tests"],
    }


def validate_candidate(code: str, function_name: str) -> dict[str, Any]:
    lowered = code.lower()
    blocked = [pattern for pattern in BLOCKED_PATTERNS if pattern in lowered]
    if blocked:
        errors = [f"blocked_pattern:{item}" for item in blocked]
        if any(item.startswith("import ") for item in blocked):
            errors.append("imports_not_allowed")
        return {"ok": False, "stage": "policy", "errors": errors}
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"ok": False, "stage": "syntax", "errors": [str(exc)]}
    functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    if function_name not in functions:
        return {"ok": False, "stage": "contract", "errors": [f"missing_function:{function_name}"]}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return {"ok": False, "stage": "policy", "errors": ["imports_not_allowed"]}
        if isinstance(node, ast.Attribute) and node.attr not in {"append","add","get","split"}:
            return {"ok": False, "stage": "policy", "errors": [f"blocked_attribute:{node.attr}"]}
        if isinstance(node, (ast.ClassDef, ast.Lambda, ast.AsyncFunctionDef, ast.Await, ast.Global, ast.Nonlocal)):
            return {"ok": False, "stage": "policy", "errors": [f"blocked_ast:{type(node).__name__}"]}
        if isinstance(node, ast.Name) and (node.id.startswith("__") or node.id in {"getattr","setattr","delattr","globals","locals","vars","compile","input","help","breakpoint"}):
            return {"ok": False, "stage": "policy", "errors": [f"blocked_name:{node.id}"]}
        if isinstance(node, ast.Constant) and isinstance(node.value,str) and "__" in node.value:
            return {"ok": False, "stage": "policy", "errors": ["blocked_dunder_literal"]}
    return {"ok": True, "stage": "validation", "errors": []}


def verify_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    if not candidate.get("tests"):
        return {"ok": False, "stage": "tests", "test_count": 0, "passed": 0, "rows": [], "reason": "tests_required"}
    namespace: dict[str, Any] = {"__builtins__": {"len": len, "range": range, "set": set}}
    exec(candidate["code"], namespace, namespace)
    fn = namespace[candidate["function_name"]]
    rows = []
    for index, test in enumerate(candidate["tests"], start=1):
        try:
            actual = fn(*test["args"])
            ok = actual == test["expected"]
            error = None
        except Exception as exc:  # pragma: no cover - defensive boundary
            actual = None
            ok = False
            error = str(exc)
        rows.append({
            "test_id": f"t{index:02d}",
            "args": test["args"],
            "expected": test["expected"],
            "actual": actual,
            "ok": ok,
            "error": error,
        })
    return {
        "ok": all(row["ok"] for row in rows),
        "stage": "tests",
        "test_count": len(rows),
        "passed": sum(1 for row in rows if row["ok"]),
        "rows": rows,
    }


def repair_hint(task: dict[str, Any], validation: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
    if validation and not validation["ok"]:
        return {"needed": True, "hint": "Fix validation errors before running tests.", "errors": validation.get("errors", [])}
    if not verification["ok"]:
        return {"needed": True, "hint": f"Recheck the {task['task_type']} algorithm against failed tests."}
    return {"needed": False, "hint": "No repair needed for the bounded fixture set."}


def run_coding_task_benchmark(cases_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in load_jsonl(cases_path):
        result = run_coding_task(case["prompt"], case.get("history", []))
        route_ok = result["route"] == case["expected_route"]
        task_ok = result["task"]["task_type"] == case["expected_task_type"]
        verification_ok = result["verification"]["ok"] == case["expected_verification_ok"]
        rows.append({
            "case_id": case["case_id"],
            "phenomenon_tags": case.get("phenomenon_tags", []),
            "route_ok": route_ok,
            "task_ok": task_ok,
            "verification_ok": verification_ok,
            "case_ok": route_ok and task_ok and verification_ok,
            "result": result,
        })
    summary = {
        "ok": all(row["case_ok"] for row in rows),
        "run_id": out.name,
        "case_count": len(rows),
        "route_accuracy": ratio(row["route_ok"] for row in rows),
        "task_accuracy": ratio(row["task_ok"] for row in rows),
        "verification_accuracy": ratio(row["verification_ok"] for row in rows),
        "case_accuracy": ratio(row["case_ok"] for row in rows),
        "by_tag": by_tag(rows),
        "claim": "bounded_coding_task_runner_only",
        "blocked_claims": blocked_claims(),
    }
    write_jsonl(out / "coding_task_rows.jsonl", rows)
    (out / "coding_task_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def response_text(route: str, task: dict[str, Any], verification: dict[str, Any], repair: dict[str, Any]) -> str:
    if route == "coding_pass":
        return f"Generated a bounded pure-function solution for {task['task_type']} and passed {verification['passed']}/{verification['test_count']} tests."
    return f"Generated code needs repair: {repair['hint']}"


def coding_output_chunks(
    prompt: str,
    route: str,
    candidate: dict[str, Any],
    verification: dict[str, Any],
    repair: dict[str, Any],
) -> list[dict[str, Any]]:
    chunks = [
        {
            "chunk_id": "out-01",
            "role": route,
            "seed": stable_seed(prompt, salt="lce-coding-route-v0"),
            "text": response_text(route, {"task_type": candidate["task_type"]}, verification, repair),
        },
        {
            "chunk_id": "out-02",
            "role": "code",
            "seed": stable_seed(candidate["code"], salt="lce-coding-code-v0"),
            "text": candidate["code"],
        },
        {
            "chunk_id": "out-03",
            "role": "verification",
            "seed": stable_seed(json.dumps(verification, sort_keys=True), salt="lce-coding-verification-v0"),
            "text": json.dumps(verification, ensure_ascii=False, indent=2),
        },
    ]
    if repair["needed"]:
        chunks.append({
            "chunk_id": "out-04",
            "role": "repair",
            "seed": stable_seed(repair["hint"], salt="lce-coding-repair-v0"),
            "text": repair["hint"],
        })
    return chunks


def blocked_claims() -> list[str]:
    return [
        "general_programming_agent",
        "arbitrary_code_execution",
        "filesystem_modification",
        "network_programming",
        "security_sensitive_code",
        "llm_quality_parity",
    ]


def ratio(values: Any) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return round(sum(1 for value in vals if value) / len(vals), 6)


def by_tag(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        for tag in row["phenomenon_tags"]:
            entry = result.setdefault(tag, {"case_count": 0, "case_ok": 0})
            entry["case_count"] += 1
            entry["case_ok"] += 1 if row["case_ok"] else 0
    for entry in result.values():
        entry["accuracy"] = round(entry["case_ok"] / entry["case_count"], 6)
    return result


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
