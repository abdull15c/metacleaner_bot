"""
Собирает исходный код проекта в один .txt (удобно для архива или контекста для ИИ).

Запуск из корня проекта:
  python scripts/dump_codebase.py
  python scripts/dump_codebase.py -o my_dump.txt
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# корень репозитория (родитель каталога scripts)
ROOT = Path(__file__).resolve().parent.parent

INCLUDE_EXTENSIONS = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".html", ".css", ".js", ".sql", ".env.example", ".gitignore",
}

SKIP_DIR_NAMES = {
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".venv", "venv", ".idea", ".cursor", "node_modules",
    "htmlcov", ".tox", "dist", "build", "*.egg-info",
}

SKIP_FILE_NAMES = {
    ".env", ".env.local", ".env.production",
}

SKIP_SUFFIXES = (".pyc", ".pyo", ".so", ".dll", ".exe", ".png", ".jpg", ".jpeg",
                 ".gif", ".webp", ".ico", ".pdf", ".zip", ".7z", ".db", ".sqlite3")

MAX_FILE_BYTES = 2 * 1024 * 1024  # пропускать файлы крупнее 2 МБ

EXTRA_NAMES = {".gitignore", "dockerfile", "makefile"}


def _kind(path: Path) -> str:
    n = path.name.lower()
    if n.endswith(".env.example"):
        return ".env.example"
    return path.suffix.lower()


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES or name.endswith(".egg-info")


def should_skip_file(path: Path) -> bool:
    name = path.name
    if name in SKIP_FILE_NAMES:
        return True
    if name.endswith(SKIP_SUFFIXES):
        return True
    nl = name.lower()
    if nl not in EXTRA_NAMES and _kind(path) not in INCLUDE_EXTENSIONS:
        return True
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return True
    except OSError:
        return True
    return False


def collect_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # обрезаем обход по skip dirs
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        base = Path(dirpath)
        for fn in filenames:
            p = base / fn
            if should_skip_file(p):
                continue
            out.append(p)
    out.sort(key=lambda x: str(x).replace("\\", "/").lower())
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Дамп исходников в один .txt")
    parser.add_argument(
        "-o", "--output",
        default=str(ROOT / "codebase_dump.txt"),
        help="Путь к выходному файлу (по умолчанию: codebase_dump.txt в корне проекта)",
    )
    parser.add_argument(
        "--root",
        default=str(ROOT),
        help="Корень проекта для обхода",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    out_path = Path(args.output).resolve()

    if not root.is_dir():
        print(f"Нет каталога: {root}", file=sys.stderr)
        return 1

    files = collect_files(root)
    sep = "=" * 80
    header = (
        f"{sep}\n"
        f"CODEBASE DUMP\n"
        f"root: {root}\n"
        f"generated_utc: {datetime.now(timezone.utc).isoformat()}\n"
        f"files: {len(files)}\n"
        f"{sep}\n\n"
    )

    lines: list[str] = [header]
    for p in files:
        rel = p.relative_to(root)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            lines.append(f"\n{sep}\nFILE: {rel}\nERROR_READ: {e}\n{sep}\n")
            continue
        lines.append(f"\n{sep}\nFILE: {rel}\n{sep}\n\n")
        lines.append(text)
        if text and not text.endswith("\n"):
            lines.append("\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(lines), encoding="utf-8", newline="\n")
    print(f"OK: {len(files)} файлов -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
