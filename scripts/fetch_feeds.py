from __future__ import annotations

import email.utils
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9), "JST")
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "sources.json"
PREFERENCES_PATH = ROOT_DIR / "config" / "preferences.json"
HISTORY_PATH = ROOT_DIR / "data" / "history.json"
OUTPUT_ROOT = ROOT_DIR / "docs"
TODAY_PATH = ROOT_DIR / "today.md"
NEW_ARTICLES_PATH = ROOT_DIR / "data" / "new_articles.json"
USER_AGENT = "jouhousyusyuu-feed-collector/1.0"


@dataclass(frozen=True)
class Source:
    name: str
    display_name: str
    type: str
    url: str
    limit: int
    category: str
    enabled: bool


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    published_at: str | None
    thumbnail_url: str | None
    description: str | None
    source_name: str
    source_display_name: str
    category: str


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")


def load_sources() -> list[Source]:
    data = load_json(CONFIG_PATH, {"sources": []})
    sources: list[Source] = []
    for item in data.get("sources", []):
        sources.append(
            Source(
                name=str(item["name"]),
                display_name=str(item.get("display_name") or item["name"]),
                type=str(item.get("type") or "rss"),
                url=str(item["url"]),
                limit=int(item.get("limit") or 10),
                category=str(item.get("category") or "uncategorized"),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return sources


def load_preferences() -> dict[str, Any]:
    return load_json(
        PREFERENCES_PATH,
        {
            "interests": [],
            "exclude_keywords": [],
            "max_summary_items": 10,
            "history_retention_days": 90,
            "github_models": {"enabled": False},
        },
    )


def fetch_xml(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", "", value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def get_text(element: ET.Element, path: str, namespaces: dict[str, str] | None = None) -> str | None:
    found = element.find(path, namespaces or {})
    if found is None or found.text is None:
        return None
    return clean_text(found.text)


def get_attr(element: ET.Element, path: str, attr: str, namespaces: dict[str, str] | None = None) -> str | None:
    found = element.find(path, namespaces or {})
    if found is None:
        return None
    value = found.attrib.get(attr)
    return clean_text(value)


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    except (TypeError, ValueError):
        return clean_text(value)


def parse_feed(xml_bytes: bytes, source: Source) -> list[Article]:
    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "media": "http://search.yahoo.com/mrss/",
    }
    root = ET.fromstring(xml_bytes)
    if root.tag.endswith("feed"):
        return parse_atom(root, namespaces, source)
    return parse_rss(root, namespaces, source)


def parse_rss(root: ET.Element, namespaces: dict[str, str], source: Source) -> list[Article]:
    items = root.findall("./channel/item")
    articles: list[Article] = []
    for item in items[: source.limit]:
        articles.append(
            Article(
                title=get_text(item, "title") or "No title",
                url=get_text(item, "link") or "",
                published_at=normalize_date(get_text(item, "pubDate")),
                thumbnail_url=get_attr(item, "media:thumbnail", "url", namespaces)
                or get_attr(item, "media:content", "url", namespaces),
                description=get_text(item, "description"),
                source_name=source.name,
                source_display_name=source.display_name,
                category=source.category,
            )
        )
    return articles


def parse_atom(root: ET.Element, namespaces: dict[str, str], source: Source) -> list[Article]:
    entries = root.findall("atom:entry", namespaces)
    articles: list[Article] = []
    for entry in entries[: source.limit]:
        url = ""
        for link in entry.findall("atom:link", namespaces):
            rel = link.attrib.get("rel", "alternate")
            href = link.attrib.get("href")
            if rel == "alternate" and href:
                url = html.unescape(href.strip())
                break
        if not url:
            url = get_attr(entry, "atom:link", "href", namespaces) or ""

        articles.append(
            Article(
                title=get_text(entry, "atom:title", namespaces) or "No title",
                url=url,
                published_at=normalize_date(
                    get_text(entry, "atom:published", namespaces)
                    or get_text(entry, "atom:updated", namespaces)
                ),
                thumbnail_url=get_attr(entry, "media:thumbnail", "url", namespaces)
                or get_attr(entry, "media:content", "url", namespaces),
                description=get_text(entry, "atom:summary", namespaces)
                or get_text(entry, "atom:content", namespaces),
                source_name=source.name,
                source_display_name=source.display_name,
                category=source.category,
            )
        )
    return articles


def article_key(article: Article) -> str:
    value = article.url or f"{article.source_name}:{article.title}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def prune_history(history: dict[str, Any], now: datetime, retention_days: int) -> dict[str, Any]:
    seen = history.get("seen", {})
    if not isinstance(seen, dict):
        seen = {}
    threshold = (now - timedelta(days=retention_days)).date()
    pruned: dict[str, Any] = {}
    for key, value in seen.items():
        first_seen = str(value.get("first_seen", "")) if isinstance(value, dict) else ""
        try:
            first_seen_date = datetime.strptime(first_seen, "%Y-%m-%d").date()
        except ValueError:
            continue
        if first_seen_date >= threshold:
            pruned[key] = value
    return {"seen": pruned}


def split_new_articles(articles: list[Article], history: dict[str, Any]) -> list[Article]:
    seen = history.get("seen", {})
    return [article for article in articles if article_key(article) not in seen]


def update_history(history: dict[str, Any], articles: list[Article], now: datetime) -> dict[str, Any]:
    seen = history.setdefault("seen", {})
    today = now.strftime("%Y-%m-%d")
    for article in articles:
        seen[article_key(article)] = {
            "title": article.title,
            "url": article.url,
            "source": article.source_display_name,
            "first_seen": today,
        }
    return history


def render_source_markdown(source: Source, articles: list[Article], fetched_at: datetime) -> str:
    date_text = fetched_at.strftime("%Y-%m-%d")
    fetched_text = fetched_at.strftime("%Y-%m-%d %H:%M:%S JST")
    lines = [
        f"# {source.display_name} {date_text}",
        "",
        f"- 取得元: {source.display_name}",
        f"- カテゴリ: {source.category}",
        f"- フィードURL: {source.url}",
        f"- 取得日時: {fetched_text}",
        f"- 取得件数: {len(articles)}",
        "",
        "## 記事一覧",
        "",
    ]
    if not articles:
        lines.extend(["記事は取得できませんでした。", ""])
        return "\n".join(lines)
    for index, article in enumerate(articles, start=1):
        lines.extend(
            [
                f"### {index}. {article.title}",
                "",
                f"- URL: {article.url or '-'}",
                f"- 公開日時: {article.published_at or '-'}",
                f"- サムネイル: {article.thumbnail_url or '-'}",
                f"- 概要: {article.description or '-'}",
                "",
            ]
        )
    return "\n".join(lines)


def write_source_markdown(source: Source, articles: list[Article], now: datetime) -> None:
    date_dir = OUTPUT_ROOT / now.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    output_path = date_dir / f"{source.name}.md"
    output_path.write_text(render_source_markdown(source, articles, now), encoding="utf-8")
    print(f"created: {output_path.relative_to(ROOT_DIR)}")


def collect_articles(sources: list[Source], now: datetime) -> tuple[list[Article], bool]:
    all_articles: list[Article] = []
    ok = True
    for source in sources:
        if source.type != "rss":
            print(f"skip unsupported source type: {source.name} ({source.type})")
            continue
        try:
            articles = parse_feed(fetch_xml(source.url), source)
            write_source_markdown(source, articles, now)
            all_articles.extend(articles)
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError, ValueError) as error:
            ok = False
            print(f"failed: {source.name}: {error}", file=sys.stderr)
            write_source_markdown(source, [], now)
    return all_articles, ok


def keyword_score(article: Article, interests: list[str], exclude_keywords: list[str]) -> tuple[int, list[str]]:
    text = f"{article.title} {article.description or ''} {article.category} {article.source_display_name}".lower()
    if any(keyword.lower() in text for keyword in exclude_keywords):
        return -1000, []
    matched = [keyword for keyword in interests if keyword.lower() in text]
    score = len(matched) * 10
    if article.category in {"company_blog", "tech", "tech_news"}:
        score += 3
    return score, matched


def fallback_select_articles(
    articles: list[Article], preferences: dict[str, Any]
) -> list[dict[str, Any]]:
    interests = [str(item) for item in preferences.get("interests", [])]
    exclude_keywords = [str(item) for item in preferences.get("exclude_keywords", [])]
    max_items = int(preferences.get("max_summary_items", 10))

    scored: list[tuple[int, list[str], Article]] = []
    for article in articles:
        score, matched = keyword_score(article, interests, exclude_keywords)
        if score > 0:
            scored.append((score, matched, article))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected: list[dict[str, Any]] = []
    for score, matched, article in scored[:max_items]:
        selected.append(
            {
                "title": article.title,
                "url": article.url,
                "source": article.source_display_name,
                "published_at": article.published_at,
                "reason": f"興味キーワードに一致: {', '.join(matched)}" if matched else "技術カテゴリの記事",
                "keywords": matched,
            }
        )
    return selected


def call_github_models(articles: list[Article], preferences: dict[str, Any]) -> list[dict[str, Any]] | None:
    model_config = preferences.get("github_models", {})
    if not model_config.get("enabled", False):
        return None

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        return None

    max_items = int(preferences.get("max_summary_items", 10))
    payload_articles = [asdict(article) for article in articles[:80]]
    prompt = {
        "interests": preferences.get("interests", []),
        "exclude_keywords": preferences.get("exclude_keywords", []),
        "max_summary_items": max_items,
        "articles": payload_articles,
    }

    request_body = {
        "model": str(model_config.get("model", "openai/gpt-4.1-mini")),
        "messages": [
            {
                "role": "system",
                "content": "あなたは技術記事の選別担当です。本文要約はしません。タイトル、出典、カテゴリ、RSS概要だけから、ユーザーが興味を持ちそうな記事を選び、JSONだけを返してください。",
            },
            {
                "role": "user",
                "content": "次の記事候補から読む価値が高そうなものを選んでください。返却形式は {\"items\":[{\"title\":...,\"url\":...,\"source\":...,\"published_at\":...,\"reason\":...,\"keywords\":[...]}]} のJSONのみ。\n"
                + json.dumps(prompt, ensure_ascii=False),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 2000,
    }

    endpoint = str(model_config.get("endpoint", "https://models.github.ai/inference/chat/completions"))
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))
        content = response_data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        items = parsed.get("items", [])
        if isinstance(items, list):
            return items[:max_items]
    except Exception as error:  # noqa: BLE001
        print(f"github models fallback: {error}", file=sys.stderr)
    return None


def render_today_markdown(
    selected_items: list[dict[str, Any]],
    new_articles: list[Article],
    all_articles_count: int,
    now: datetime,
    used_model: bool,
) -> str:
    fetched_text = now.strftime("%Y-%m-%d %H:%M:%S JST")
    lines = [
        "# 今日の記事サマリー",
        "",
        f"- 取得日時: {fetched_text}",
        f"- 全取得記事数: {all_articles_count}",
        f"- 新規記事数: {len(new_articles)}",
        f"- 選定方式: {'GitHub Models' if used_model else 'キーワード一致フォールバック'}",
        "",
        "## 今日見る候補",
        "",
    ]

    if not selected_items:
        lines.extend(["条件に一致する新規記事はありませんでした。", ""])
    else:
        for index, item in enumerate(selected_items, start=1):
            keywords = item.get("keywords") or []
            if isinstance(keywords, list):
                keyword_text = ", ".join(str(keyword) for keyword in keywords) or "-"
            else:
                keyword_text = str(keywords)
            lines.extend(
                [
                    f"### {index}. {item.get('title', 'No title')}",
                    "",
                    f"- 出典: {item.get('source', '-')}",
                    f"- URL: {item.get('url', '-')}",
                    f"- 公開日時: {item.get('published_at') or '-'}",
                    f"- 理由: {item.get('reason') or '-'}",
                    f"- 関連キーワード: {keyword_text}",
                    "",
                ]
            )

    lines.extend(["## 新規記事一覧", ""])
    if not new_articles:
        lines.extend(["新規記事はありませんでした。", ""])
    else:
        for article in new_articles:
            lines.append(f"- [{article.title}]({article.url}) - {article.source_display_name}")
        lines.append("")

    return "\n".join(lines)


def write_today_files(markdown: str, now: datetime) -> None:
    TODAY_PATH.write_text(markdown, encoding="utf-8")
    summary_dir = OUTPUT_ROOT / now.strftime("%Y-%m-%d")
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "summary.md").write_text(markdown, encoding="utf-8")
    print("created: today.md")
    print(f"created: {(summary_dir / 'summary.md').relative_to(ROOT_DIR)}")


def main() -> int:
    now = datetime.now(JST)
    preferences = load_preferences()
    sources = [source for source in load_sources() if source.enabled]
    if not sources:
        print("no enabled sources")
        return 1

    history = load_json(HISTORY_PATH, {"seen": {}})
    history = prune_history(
        history,
        now,
        int(preferences.get("history_retention_days", 90)),
    )

    all_articles, ok = collect_articles(sources, now)
    new_articles = split_new_articles(all_articles, history)
    write_json(NEW_ARTICLES_PATH, {"articles": [asdict(article) for article in new_articles]})

    model_items = call_github_models(new_articles, preferences) if new_articles else None
    used_model = model_items is not None
    selected_items = model_items or fallback_select_articles(new_articles, preferences)
    today_markdown = render_today_markdown(
        selected_items,
        new_articles,
        len(all_articles),
        now,
        used_model,
    )
    write_today_files(today_markdown, now)

    history = update_history(history, new_articles, now)
    write_json(HISTORY_PATH, history)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
