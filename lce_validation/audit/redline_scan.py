from __future__ import annotations

from pathlib import Path
from typing import Any

PROHIBITED = [
    "attention is replaced",
    "Transformer is unnecessary",
    "GPU is no longer needed",
    "CPU/Pi feasibility is proven",
    "precision is maintained",
    "Japanese behavior is preserved",
    "dataset minimum is established",
    "verifier proves correctness",
    "watchdog proves independence",
    "benchmark improvement is demonstrated",
]

NEGATION_GUARDS = [
    "must not",
    "does not claim",
    "do not claim",
    "not claim",
    "forbidden",
    "prohibited",
    "blocked",
    "unsupported",
    "red-line",
    "red line",
    "claim lock",
    "no ",
]


def scan_text(text: str, artifact_ref: str = "text") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    lower = text.lower()
    for phrase in PROHIBITED:
        phrase_lower = phrase.lower()
        start = lower.find(phrase_lower)
        if start >= 0 and not _is_guarded_context(lower, start, len(phrase_lower)):
            rows.append({
                "scan_row_id": f"scan-{artifact_ref}-{len(rows)+1}",
                "artifact_ref": artifact_ref,
                "scan_scope": "text",
                "prohibited_phrase": phrase,
                "matched_text_ref": phrase,
                "severity": "P0",
                "claim_type": "red_line",
                "evidence_required": "row_level_registered_evidence",
                "result": "violation",
            })
    return rows


def _is_guarded_context(lower_text: str, start: int, length: int) -> bool:
    line_start = lower_text.rfind("\n", 0, start) + 1
    line_end = lower_text.find("\n", start)
    if line_end < 0:
        line_end = len(lower_text)
    line = lower_text[line_start:line_end].strip()
    if line.startswith(("- \"", "- '", "- `", "* \"", "* '", "* `")):
        return True
    left = max(0, start - 160)
    right = min(len(lower_text), start + length + 80)
    context = lower_text[left:right]
    return any(guard in context for guard in NEGATION_GUARDS)


def scan_path(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if p.is_dir():
        rows: list[dict[str, Any]] = []
        for child in p.rglob("*.md"):
            rows.extend(scan_text(child.read_text(encoding="utf-8"), artifact_ref=str(child)))
        return rows
    return scan_text(p.read_text(encoding="utf-8"), artifact_ref=str(p))
