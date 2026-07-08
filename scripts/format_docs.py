from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9), "JST")
ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_ROOT = ROOT_DIR / "docs"


def find_url(lines: list[str], start_index: int) -> str | None:
    for line in lines[start_index : start_index + 8]:
        if line.startswith("- URL: "):
            url = line.replace("- URL: ", "", 1).strip()
            if url and url != "-":
                return url
    return None


def format_text(text: str) -> str:
    lines = text.splitlines()
    formatted: list[str] = []

    for index, line in enumerate(lines):
        if line.startswith("- 概要: "):
            continue

        if line.startswith("### ") and ". " in line:
            prefix, title = line.split(". ", 1)
            if title.startswith("["):
                formatted.append(line)
                continue
            url = find_url(lines, index + 1)
            if url:
                formatted.append(f"{prefix}. [{title}]({url})")
                continue

        formatted.append(line)

    return "\n".join(formatted).rstrip() + "\n"


def main() -> int:
    target_dir = DOCS_ROOT / datetime.now(JST).strftime("%Y-%m-%d")
    if not target_dir.exists():
        print("docs target directory does not exist")
        return 0

    for path in target_dir.glob("*.md"):
        if path.name == "summary.md":
            continue
        before = path.read_text(encoding="utf-8")
        after = format_text(before)
        if before != after:
            path.write_text(after, encoding="utf-8")
            print(f"formatted: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
