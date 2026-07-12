"""Build a deterministic source ZIP for the v0.1.0-alpha release candidate."""
from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".grenade", ".lce-data", ".lce_data", ".lce_runs", ".pytest_cache", "__pycache__", ".venv", "venv", "build", "dist"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
FIXED_ZIP_TIME = (2026, 7, 12, 0, 0, 0)


def iter_release_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def build_archive(output: Path, root_name: str = "LCE-0.1.0-alpha") -> list[str]:
    output.parent.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in iter_release_files(ROOT):
            arcname = f"{root_name}/{path.relative_to(ROOT).as_posix()}"
            info = ZipInfo(arcname, FIXED_ZIP_TIME)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
            names.append(arcname)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="dist/LCE-0.1.0-alpha.zip")
    args = parser.parse_args()
    names = build_archive(Path(args.out))
    print(f"RELEASE_ARCHIVE_BUILT files={len(names)} path={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
