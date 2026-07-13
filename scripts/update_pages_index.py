from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9), "JST")
ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_ROOT = ROOT_DIR / "docs"
INDEX_PATH = DOCS_ROOT / "index.md"
DATE_DIR_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_HISTORY_DAYS = 60

FILE_LABELS = {
    "summary.md": "おすすめ記事サマリー",
    "frontend-summary.md": "フロントエンド脆弱性サマリー",
    "backend-summary.md": "バックエンド脆弱性サマリー",
    "yahoo.md": "Yahoo!ニュース",
    "qiita.md": "Qiita",
    "zenn.md": "Zenn",
}


def discover_date_directories() -> list[Path]:
    if not DOCS_ROOT.exists():
        return []

    return sorted(
        (
            path
            for path in DOCS_ROOT.iterdir()
            if path.is_dir() and DATE_DIR_PATTERN.fullmatch(path.name)
        ),
        key=lambda path: path.name,
        reverse=True,
    )


def markdown_files(date_dir: Path) -> list[Path]:
    priority = {
        "summary.md": 0,
        "frontend-summary.md": 1,
        "backend-summary.md": 2,
    }
    return sorted(
        date_dir.glob("*.md"),
        key=lambda path: (priority.get(path.name, 10), path.name),
    )


def page_label(path: Path) -> str:
    if path.name in FILE_LABELS:
        return FILE_LABELS[path.name]

    name = path.stem.replace("-", " ").replace("_", " ").strip()
    return name or path.name


def markdown_link(path: Path) -> str:
    return path.relative_to(DOCS_ROOT).as_posix()


def build_index(now: datetime) -> str:
    date_dirs = discover_date_directories()
    lines = [
        "# 情報収集ダイジェスト",
        "",
        "GitHub Actions が収集したニュース・技術記事・脆弱性情報を日付別に閲覧できます。",
        "",
        f"最終生成: {now.strftime('%Y-%m-%d %H:%M:%S JST')}",
        "",
    ]

    if not date_dirs:
        lines.extend(["## 記事", "", "まだ記事が生成されていません。", ""])
        return "\n".join(lines)

    latest_dir = date_dirs[0]
    latest_files = markdown_files(latest_dir)
    lines.extend([f"## 最新: {latest_dir.name}", ""])

    if latest_files:
        for path in latest_files:
            lines.append(f"- [{page_label(path)}]({markdown_link(path)})")
    else:
        lines.append("この日付の記事ファイルはまだありません。")

    lines.extend(["", "## 過去の記事", ""])
    for date_dir in date_dirs[1 : MAX_HISTORY_DAYS + 1]:
        files = markdown_files(date_dir)
        if not files:
            continue

        preferred = next((path for path in files if path.name == "summary.md"), files[0])
        lines.append(f"- [{date_dir.name}]({markdown_link(preferred)})")

    lines.extend(
        [
            "",
            "---",
            "",
            "このページは公開時に自動生成されます。元データはリポジトリの `docs/` に保存されています。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(build_index(datetime.now(JST)), encoding="utf-8")
    print(f"generated: {INDEX_PATH.relative_to(ROOT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
