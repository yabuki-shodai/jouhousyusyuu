from __future__ import annotations

import email.utils
import hashlib
import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9), "JST")
ROOT_DIR = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT_DIR / "config" / "sources.json"
PREFERENCES_PATH = ROOT_DIR / "config" / "preferences.json"
HISTORY_PATH = ROOT_DIR / "data" / "history.json"
TODAY_PATH = ROOT_DIR / "today.md"
DOCS_ROOT = ROOT_DIR / "docs"
USER_AGENT = "jouhousyusyuu-today-builder/1.0"


@dataclass(frozen=True)
class Source:
    name: str
    display_name: str
    url: str
    limit: int
    category: str
    enabled: bool


@dataclass(frozen=True)
class Article:
    id: str
    title: str
    url: str
    source: str
    category: str
    description: str | None
    published_at: str | None


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def clean(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def article_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    except (TypeError, ValueError):
        return clean(value)


def text(el: ET.Element, path: str, ns: dict[str, str]) -> str | None:
    found = el.find(path, ns)
    if found is None:
        return None
    return clean(found.text)


def load_sources() -> list[Source]:
    data = load_json(SOURCES_PATH, {"sources": []})
    result: list[Source] = []
    for item in data.get("sources", []):
        result.append(
            Source(
                name=str(item["name"]),
                display_name=str(item.get("display_name") or item["name"]),
                url=str(item["url"]),
                limit=int(item.get("limit", 10)),
                category=str(item.get("category", "uncategorized")),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return result


def fetch_feed(url: str) -> ET.Element:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
        return ET.fromstring(res.read())


def parse_source(source: Source) -> list[Article]:
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "dc": "http://purl.org/dc/elements/1.1/",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }
    root = fetch_feed(source.url)
    articles: list[Article] = []

    if root.tag.endswith("feed"):
        entries = root.findall("atom:entry", ns)
        for entry in entries[: source.limit]:
            title = text(entry, "atom:title", ns) or "No title"
            link = ""
            for link_el in entry.findall("atom:link", ns):
                if link_el.attrib.get("rel", "alternate") == "alternate" and link_el.attrib.get("href"):
                    link = link_el.attrib["href"].strip()
                    break
            if not link:
                continue
            description = text(entry, "atom:summary", ns) or text(entry, "atom:content", ns)
            published_at = normalize_date(text(entry, "atom:published", ns) or text(entry, "atom:updated", ns))
            articles.append(Article(article_id(link), title, link, source.display_name, source.category, description, published_at))
        return articles

    items = root.findall("./channel/item")
    for item in items[: source.limit]:
        title = text(item, "title", ns) or "No title"
        link = text(item, "link", ns)
        if not link:
            continue
        description = text(item, "description", ns) or text(item, "content:encoded", ns)
        published_at = normalize_date(text(item, "pubDate", ns) or text(item, "dc:date", ns))
        articles.append(Article(article_id(link), title, link, source.display_name, source.category, description, published_at))
    return articles


def prune_history(history: dict[str, Any], now: datetime, retention_days: int) -> dict[str, Any]:
    threshold = now.date() - timedelta(days=retention_days)
    pruned = {}
    for key, value in history.get("seen", {}).items():
        try:
            first_seen = datetime.strptime(value.get("first_seen", ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        if first_seen >= threshold:
            pruned[key] = value
    return {"seen": pruned}


def keyword_select(articles: list[Article], prefs: dict[str, Any]) -> list[dict[str, Any]]:
    interests = [str(x) for x in prefs.get("interests", [])]
    excludes = [str(x).lower() for x in prefs.get("exclude_keywords", [])]
    max_items = int(prefs.get("max_summary_items", 10))
    scored = []
    for article in articles:
        target = f"{article.title} {article.description or ''} {article.source} {article.category}".lower()
        if any(x in target for x in excludes):
            continue
        matched = [x for x in interests if x.lower() in target]
        if matched:
            scored.append((len(matched), article, matched))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "category": a.category,
            "published_at": a.published_at,
            "reason": "興味キーワードに一致: " + ", ".join(m[:5]),
            "keywords": m[:5],
        }
        for _, a, m in scored[:max_items]
    ]


def model_select(articles: list[Article], prefs: dict[str, Any]) -> list[dict[str, Any]]:
    config = prefs.get("github_models", {})
    if not config.get("enabled", False):
        raise RuntimeError("model disabled")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is empty")

    payload = {
        "model": str(config.get("model", "openai/gpt-4.1-mini")),
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": "記事本文は読まず、タイトル・出典・カテゴリ・RSS概要だけで興味がありそうな記事を選び、JSONのみ返してください。形式は {\"items\":[{\"id\":\"...\",\"reason\":\"...\",\"keywords\":[\"...\"]}]} です。",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "interests": prefs.get("interests", []),
                        "exclude_keywords": prefs.get("exclude_keywords", []),
                        "max_summary_items": prefs.get("max_summary_items", 10),
                        "articles": [a.__dict__ for a in articles],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    req = urllib.request.Request(
        str(config.get("endpoint", "https://models.github.ai/inference/chat/completions")),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        data = json.loads(res.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    selected = json.loads(content).get("items", [])
    article_map = {a.id: a for a in articles}
    result = []
    for item in selected:
        article = article_map.get(str(item.get("id")))
        if not article:
            continue
        result.append(
            {
                "id": article.id,
                "title": article.title,
                "url": article.url,
                "source": article.source,
                "category": article.category,
                "published_at": article.published_at,
                "reason": str(item.get("reason") or "興味ありと判定"),
                "keywords": [str(x) for x in item.get("keywords", [])],
            }
        )
    return result[: int(prefs.get("max_summary_items", 10))]


def select_articles(articles: list[Article], prefs: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    try:
        selected = model_select(articles, prefs)
        if selected:
            return selected, "github_models"
    except Exception as e:
        print(f"GitHub Models failed. fallback used: {e}", file=sys.stderr)
    return keyword_select(articles, prefs), "keyword_fallback"


def render_today(selected: list[dict[str, Any]], new_articles: list[Article], now: datetime, selector: str) -> str:
    lines = [
        "# 今日の記事サマリー",
        "",
        f"取得日時: {now.strftime('%Y-%m-%d %H:%M:%S JST')}",
        "",
        "## 集計",
        "",
        f"- 新規記事数: {len(new_articles)}",
        f"- サマリー選定数: {len(selected)}",
        f"- 選定方式: {selector}",
        "",
        "## 今日見る候補",
        "",
    ]
    if not selected:
        lines += ["候補記事はありません。", ""]
    for i, item in enumerate(selected, 1):
        lines += [
            f"### {i}. {item['title']}",
            "",
            f"- 出典: {item['source']}",
            f"- カテゴリ: {item['category']}",
            f"- URL: {item['url']}",
            f"- 公開日時: {item.get('published_at') or '-'}",
            f"- 理由: {item['reason']}",
            f"- 関連キーワード: {', '.join(item.get('keywords') or []) or '-'}",
            "",
        ]
    lines += ["## 新規記事一覧", ""]
    grouped: dict[str, list[Article]] = {}
    for article in new_articles:
        grouped.setdefault(article.source, []).append(article)
    for source, items in grouped.items():
        lines += [f"### {source}", ""]
        for article in items:
            lines.append(f"- [{article.title}]({article.url})")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    now = datetime.now(JST)
    prefs = load_json(PREFERENCES_PATH, {})
    history = prune_history(load_json(HISTORY_PATH, {"seen": {}}), now, int(prefs.get("history_retention_days", 90)))
    seen_ids = set(history.get("seen", {}).keys())

    articles: list[Article] = []
    for source in load_sources():
        if not source.enabled:
            continue
        try:
            articles.extend(parse_source(source))
        except Exception as e:
            print(f"failed to parse {source.name}: {e}", file=sys.stderr)

    new_articles = [a for a in articles if a.id not in seen_ids]
    selected, selector = select_articles(new_articles, prefs)
    markdown = render_today(selected, new_articles, now, selector)

    TODAY_PATH.write_text(markdown, encoding="utf-8")
    summary_path = DOCS_ROOT / now.strftime("%Y-%m-%d") / "summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(markdown, encoding="utf-8")

    today = now.strftime("%Y-%m-%d")
    for article in new_articles:
        history.setdefault("seen", {})[article.id] = {
            "url": article.url,
            "title": article.title,
            "source": article.source,
            "first_seen": today,
        }
    save_json(HISTORY_PATH, history)
    print(f"new_articles={len(new_articles)} selected={len(selected)} selector={selector}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
