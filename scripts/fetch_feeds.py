from __future__ import annotations

import email.utils
import html
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9), "JST")
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "sources.json"
OUTPUT_ROOT = ROOT_DIR / "docs"
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


def load_sources() -> list[Source]:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)

    sources: list[Source] = []
    for item in data.get("sources", []):
        source = Source(
            name=str(item["name"]),
            display_name=str(item.get("display_name") or item["name"]),
            type=str(item.get("type") or "rss"),
            url=str(item["url"]),
            limit=int(item.get("limit") or 10),
            category=str(item.get("category") or "uncategorized"),
            enabled=bool(item.get("enabled", True)),
        )
        sources.append(source)
    return sources


def fetch_xml(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def get_text(element: ET.Element, path: str, namespaces: dict[str, str] | None = None) -> str | None:
    found = element.find(path, namespaces or {})
    if found is None or found.text is None:
        return None
    text = html.unescape(found.text.strip())
    return text or None


def get_attr(element: ET.Element, path: str, attr: str, namespaces: dict[str, str] | None = None) -> str | None:
    found = element.find(path, namespaces or {})
    if found is None:
        return None
    value = found.attrib.get(attr)
    if value is None:
        return None
    value = html.unescape(value.strip())
    return value or None


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None

    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    except (TypeError, ValueError):
        return value


def parse_feed(xml_bytes: bytes, limit: int) -> list[Article]:
    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "media": "http://search.yahoo.com/mrss/",
    }

    root = ET.fromstring(xml_bytes)

    if root.tag.endswith("feed"):
        return parse_atom(root, namespaces, limit)

    return parse_rss(root, namespaces, limit)


def parse_rss(root: ET.Element, namespaces: dict[str, str], limit: int) -> list[Article]:
    items = root.findall("./channel/item")
    articles: list[Article] = []

    for item in items[:limit]:
        title = get_text(item, "title") or "No title"
        url = get_text(item, "link") or ""
        published_at = normalize_date(get_text(item, "pubDate"))
        thumbnail_url = (
            get_attr(item, "media:thumbnail", "url", namespaces)
            or get_attr(item, "media:content", "url", namespaces)
            or get_text(item, "enclosure")
        )

        articles.append(
            Article(
                title=title,
                url=url,
                published_at=published_at,
                thumbnail_url=thumbnail_url,
            )
        )

    return articles


def parse_atom(root: ET.Element, namespaces: dict[str, str], limit: int) -> list[Article]:
    entries = root.findall("atom:entry", namespaces)
    articles: list[Article] = []

    for entry in entries[:limit]:
        title = get_text(entry, "atom:title", namespaces) or "No title"
        url = ""
        for link in entry.findall("atom:link", namespaces):
            rel = link.attrib.get("rel", "alternate")
            href = link.attrib.get("href")
            if rel == "alternate" and href:
                url = html.unescape(href.strip())
                break
        if not url:
            url = get_attr(entry, "atom:link", "href", namespaces) or ""

        published_at = normalize_date(
            get_text(entry, "atom:published", namespaces)
            or get_text(entry, "atom:updated", namespaces)
        )
        thumbnail_url = (
            get_attr(entry, "media:thumbnail", "url", namespaces)
            or get_attr(entry, "media:content", "url", namespaces)
        )

        articles.append(
            Article(
                title=title,
                url=url,
                published_at=published_at,
                thumbnail_url=thumbnail_url,
            )
        )

    return articles


def render_markdown(source: Source, articles: list[Article], fetched_at: datetime) -> str:
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
        lines.append("記事は取得できませんでした。")
        lines.append("")
        return "\n".join(lines)

    for index, article in enumerate(articles, start=1):
        lines.extend(
            [
                f"### {index}. {article.title}",
                "",
                f"- URL: {article.url or '-'}",
                f"- 公開日時: {article.published_at or '-'}",
                f"- サムネイル: {article.thumbnail_url or '-'}",
                "",
            ]
        )

    return "\n".join(lines)


def write_markdown(source: Source, markdown: str, now: datetime) -> Path:
    date_dir = OUTPUT_ROOT / now.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    output_path = date_dir / f"{source.name}.md"
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def collect_source(source: Source, now: datetime) -> bool:
    if source.type != "rss":
        print(f"skip unsupported source type: {source.name} ({source.type})")
        return True

    try:
        xml_bytes = fetch_xml(source.url)
        articles = parse_feed(xml_bytes, source.limit)
        markdown = render_markdown(source, articles, now)
        output_path = write_markdown(source, markdown, now)
        print(f"created: {output_path.relative_to(ROOT_DIR)}")
        return True
    except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError, ValueError) as error:
        print(f"failed: {source.name}: {error}", file=sys.stderr)
        markdown = render_markdown(source, [], now)
        output_path = write_markdown(source, markdown, now)
        print(f"created fallback: {output_path.relative_to(ROOT_DIR)}")
        return False


def main() -> int:
    now = datetime.now(JST)
    sources = [source for source in load_sources() if source.enabled]

    if not sources:
        print("no enabled sources")
        return 1

    results = [collect_source(source, now) for source in sources]
    if not all(results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
