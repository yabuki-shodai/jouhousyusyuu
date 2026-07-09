from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9), "JST")
ROOT_DIR = Path(__file__).resolve().parent.parent
README_PATH = ROOT_DIR / "README.md"

START_MARKER = "<!-- today-summary-link:start -->"
END_MARKER = "<!-- today-summary-link:end -->"


def build_today_link(now: datetime) -> str:
    date_text = now.strftime("%Y-%m-%d")
    return "\n".join(
        [
            START_MARKER,
            f"[今日の記事サマリー（{date_text}）](docs/{date_text}/summary.md)",
            END_MARKER,
        ]
    )


def update_readme(now: datetime) -> None:
    if not README_PATH.exists():
        raise FileNotFoundError(f"README.md not found: {README_PATH}")

    content = README_PATH.read_text(encoding="utf-8")
    today_link = build_today_link(now)

    if START_MARKER in content and END_MARKER in content:
        start = content.index(START_MARKER)
        end = content.index(END_MARKER) + len(END_MARKER)
        updated = content[:start] + today_link + content[end:]
    else:
        lines = content.splitlines()
        if lines and lines[0].startswith("# "):
            updated_lines = [lines[0], "", today_link, *lines[1:]]
        else:
            updated_lines = [today_link, "", *lines]
        updated = "\n".join(updated_lines)
        if content.endswith("\n"):
            updated += "\n"

    README_PATH.write_text(updated, encoding="utf-8")
    print(f"updated: {README_PATH.relative_to(ROOT_DIR)}")


def main() -> int:
    update_readme(datetime.now(JST))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
