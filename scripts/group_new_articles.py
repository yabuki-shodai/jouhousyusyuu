from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9), "JST")
ROOT_DIR = Path(__file__).resolve().parent.parent
NEW_ARTICLES_PATH = ROOT_DIR / "data" / "new_articles.json"
TODAY_PATH = ROOT_DIR / "today.md"
OUTPUT_ROOT = ROOT_DIR / "docs"

CATEGORY_LABELS = {
    "general": "総合",
    "politics": "政治",
    "world": "国際・外交",
    "business": "経済・ビジネス",
    "cybersecurity": "サイバーセキュリティ",
    "technology": "IT・AI",
    "science": "科学・宇宙",
    "health": "医療・健康",
    "anime": "アニメ・漫画",
    "history": "歴史・考古",
    "education": "教育",
    "society": "社会・事件",
    "sports": "スポーツ",
    "culture": "文化・芸術",
}


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category)


def load_articles() -> list[dict[str, Any]]:
    if not NEW_ARTICLES_PATH.exists():
        return []
    data = json.loads(NEW_ARTICLES_PATH.read_text(encoding="utf-8"))
    articles = data.get("articles", [])
    if not isinstance(articles, list):
        return []
    return [article for article in articles if isinstance(article, dict)]


def render_grouped_articles(articles: list[dict[str, Any]]) -> str:
    lines = ["## 新規記事一覧", ""]
    if not articles:
        return "\n".join(lines + ["新規記事はありませんでした。", ""])

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in articles:
        category = str(article.get("category") or "general")
        grouped[category].append(article)

    ordered_categories = [category for category in CATEGORY_LABELS if category in grouped]
    ordered_categories.extend(sorted(category for category in grouped if category not in CATEGORY_LABELS))

    for category in ordered_categories:
        category_articles = grouped[category]
        lines.extend([f"### {category_label(category)} ({len(category_articles)}件)", ""])
        for article in category_articles:
            title = str(article.get("title") or "No title")
            url = str(article.get("url") or "")
            source = str(article.get("source_display_name") or article.get("source") or "-")
            title_text = f"[{title}]({url})" if url else title
            lines.append(f"- {title_text} - {source}")
        lines.append("")

    return "\n".join(lines)


def replace_new_articles_section(markdown: str, section: str) -> str:
    marker = "## 新規記事一覧"
    if marker not in markdown:
        return markdown.rstrip() + "\n\n" + section.rstrip() + "\n"
    prefix = markdown.split(marker, 1)[0].rstrip()
    return prefix + "\n\n" + section.rstrip() + "\n"


def main() -> int:
    articles = load_articles()
    section = render_grouped_articles(articles)

    if not TODAY_PATH.exists():
        print("skip: today.md does not exist")
        return 0

    today_markdown = replace_new_articles_section(TODAY_PATH.read_text(encoding="utf-8"), section)
    TODAY_PATH.write_text(today_markdown, encoding="utf-8")

    summary_path = OUTPUT_ROOT / datetime.now(JST).strftime("%Y-%m-%d") / "summary.md"
    if summary_path.exists():
        summary_markdown = replace_new_articles_section(summary_path.read_text(encoding="utf-8"), section)
        summary_path.write_text(summary_markdown, encoding="utf-8")

    print(f"grouped {len(articles)} new articles by category")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
