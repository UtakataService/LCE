"""Reject common local-workspace artifacts from the public Git staging tree."""
from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORIES = {".grenade", ".lce_data", ".lce-data", ".lce_runs", ".pytest_cache", "__pycache__", ".venv", "venv"}
TEXT_SUFFIXES = {".md", ".py", ".json", ".jsonl", ".toml", ".yml", ".yaml", ".sql", ".txt"}
LOCAL_PATTERNS = (
    re.compile(r"[A-Z]:\\Users\\", re.IGNORECASE),
    re.compile(r"[A-Z]:/Users/", re.IGNORECASE),
    re.compile(r"Documents[\\/]Codex", re.IGNORECASE),
    re.compile(r"\\.codex[\\/]", re.IGNORECASE),
    re.compile(r"192\.168\.2\.(10|18)"),
)


def main() -> int:
    failures: list[str] = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if path.is_dir() and path.name in EXCLUDED_DIRECTORIES:
            failures.append(f"EXCLUDED_DIRECTORY:{relative}")
            continue
        if path.is_dir() and path.name == ".git" and path != ROOT / ".git":
            failures.append(f"NESTED_GIT_DIRECTORY:{relative}")
            continue
        if relative == Path("scripts/verify_public_tree.py"):
            continue
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in LOCAL_PATTERNS:
            if pattern.search(text):
                failures.append(f"LOCAL_IDENTIFIER:{relative}:{pattern.pattern}")
    if failures:
        print("PUBLIC_TREE_CHECK_FAILED")
        print("\n".join(sorted(failures)))
        return 1
    print("PUBLIC_TREE_CHECK_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
