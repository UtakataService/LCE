"""Replayable stateful episode evaluator for the bounded daily dialogue runtime."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..runtime.daily_dialogue import respond_daily_dialogue


def run_stateful_episode_benchmark(cases_path: str | Path, out_dir: str | Path, *, split: str = "development") -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for line in Path(cases_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        if case["split"] != split:
            continue
        history: list[dict[str, Any]] = []
        results = []
        for turn in case["turns"]:
            result = respond_daily_dialogue(turn["text"], history)
            results.append(result)
            history.extend([{"speaker": "user", "text": turn["text"]}, {"speaker": "assistant", "daily_dialogue_state": result["daily_dialogue_state"]}])
        final = results[-1]
        expected_acts = case.get("expected_acts", [])
        checks = {
            "act_sequence": not expected_acts or [item["dialogue_act"] for item in results] == expected_acts,
            "terminal": final["completion"]["terminal"] == case["expected_terminal"],
            "deterministic": _stable(results) == _stable(_replay(case)),
            "reference": not case.get("require_reference") or bool(final["daily_dialogue_state"]["references"]),
            "correction": not case.get("require_correction") or bool(final["daily_dialogue_state"]["corrections"]),
            "language": final["response"].isascii() if case["language"] == "en" else bool(final["response"]),
        }
        rows.append({"episode_id": case["episode_id"], "language": case["language"], "checks": checks, "result": final, "case_ok": all(checks.values())})
    summary = {
        "split": split,
        "case_count": len(rows),
        "case_accuracy": _ratio(row["case_ok"] for row in rows),
        "determinism_accuracy": _ratio(row["checks"]["deterministic"] for row in rows),
        "english_case_count": sum(row["language"] == "en" for row in rows),
        "japanese_case_count": sum(row["language"] == "ja" for row in rows),
        "claim": "bounded_stateful_episode_baseline_only",
    }
    (out / "stateful_episode_rows.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    (out / "stateful_episode_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _replay(case: dict[str, Any]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    results = []
    for turn in case["turns"]:
        result = respond_daily_dialogue(turn["text"], history)
        results.append(result)
        history.extend([{"speaker": "user", "text": turn["text"]}, {"speaker": "assistant", "daily_dialogue_state": result["daily_dialogue_state"]}])
    return results


def _ratio(values: Any) -> float:
    items = list(values)
    return round(sum(bool(value) for value in items) / len(items), 6) if items else 0.0


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable(item) for key, item in value.items() if key != "latency_ms"}
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value
