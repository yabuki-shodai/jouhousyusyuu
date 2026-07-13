from __future__ import annotations

import html
import posixpath
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
OUTPUT_DIR = ROOT / "site"
SITE_TITLE = "情報収集ダイジェスト"

INLINE_TOKEN_RE = re.compile(r"`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)")
BARE_URL_RE = re.compile(r"https?://[^\s<>()]+")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LIST_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s*```(?:\w+)?\s*$")
DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CSS = r"""
:root {
  color-scheme: light dark;
  --bg: #f4f6f8;
  --surface: #ffffff;
  --surface-muted: #eef2f5;
  --text: #18212b;
  --muted: #66717d;
  --border: #d9e0e6;
  --accent: #1769aa;
  --accent-hover: #0f4f82;
  --shadow: 0 10px 30px rgba(24, 33, 43, 0.08);
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #11161c;
    --surface: #182029;
    --surface-muted: #202a35;
    --text: #edf2f6;
    --muted: #a8b2bd;
    --border: #34404c;
    --accent: #7fc4ff;
    --accent-hover: #a9d8ff;
    --shadow: 0 12px 32px rgba(0, 0, 0, 0.25);
  }
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans JP", sans-serif;
  line-height: 1.75;
}
a { color: var(--accent); text-underline-offset: 0.18em; }
a:hover { color: var(--accent-hover); }
.site-header {
  position: sticky;
  top: 0;
  z-index: 10;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  backdrop-filter: blur(12px);
}
.site-header__inner, .site-footer__inner, main {
  width: min(100% - 32px, 980px);
  margin-inline: auto;
}
.site-header__inner {
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}
.brand { color: var(--text); font-weight: 750; text-decoration: none; }
nav { display: flex; gap: 18px; font-size: 0.94rem; }
main { padding-block: 40px 64px; }
.page {
  padding: clamp(22px, 4vw, 46px);
  border: 1px solid var(--border);
  border-radius: 18px;
  background: var(--surface);
  box-shadow: var(--shadow);
}
h1, h2, h3, h4 { line-height: 1.35; scroll-margin-top: 88px; }
h1 { margin-top: 0; font-size: clamp(1.8rem, 4vw, 2.7rem); }
h2 { margin-top: 2.4em; padding-bottom: 0.35em; border-bottom: 1px solid var(--border); }
h3 {
  margin-top: 1.6em;
  padding: 0.8em 1em;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface-muted);
}
ul, ol { padding-left: 1.5em; }
li + li { margin-top: 0.35em; }
code {
  padding: 0.12em 0.35em;
  border-radius: 5px;
  background: var(--surface-muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
pre {
  overflow-x: auto;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface-muted);
}
pre code { padding: 0; background: transparent; }
blockquote {
  margin-inline: 0;
  padding: 0.1em 1em;
  border-left: 4px solid var(--accent);
  color: var(--muted);
}
.archive-group {
  margin-top: 28px;
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface-muted);
}
.archive-group h2 { margin-top: 0; }
.file-meta { color: var(--muted); font-size: 0.9rem; }
.site-footer { border-top: 1px solid var(--border); color: var(--muted); }
.site-footer__inner { padding-block: 24px 40px; font-size: 0.88rem; }
.empty { color: var(--muted); }
@media (max-width: 640px) {
  .site-header__inner { min-height: 58px; }
  nav { gap: 12px; }
  main { width: min(100% - 20px, 980px); padding-top: 20px; }
  .page { border-radius: 12px; padding: 20px; }
}
""".strip()


def safe_href(raw_href: str) -> tuple[str, bool]:
    href = raw_href.strip()
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https", "mailto"}:
        return "#", False
    if not parsed.scheme and href.lower().endswith(".md"):
        href = href[:-3] + ".html"
    external = parsed.scheme.lower() in {"http", "https"}
    return html.escape(href, quote=True), external


def linkify_text(text: str) -> str:
    output: list[str] = []
    position = 0
    for match in BARE_URL_RE.finditer(text):
        output.append(html.escape(text[position:match.start()]))
        raw_url = match.group(0).rstrip(".,;:!?、。")
        trailing = match.group(0)[len(raw_url):]
        href, _ = safe_href(raw_url)
        output.append(
            f'<a href="{href}" target="_blank" rel="noopener noreferrer">'
            f"{html.escape(raw_url)}</a>{html.escape(trailing)}"
        )
        position = match.end()
    output.append(html.escape(text[position:]))
    return "".join(output)


def render_inline(text: str) -> str:
    output: list[str] = []
    position = 0
    for match in INLINE_TOKEN_RE.finditer(text):
        output.append(linkify_text(text[position:match.start()]))
        code_text, label, raw_href = match.groups()
        if code_text is not None:
            output.append(f"<code>{html.escape(code_text)}</code>")
        else:
            href, external = safe_href(raw_href)
            attrs = ' target="_blank" rel="noopener noreferrer"' if external else ""
            output.append(f'<a href="{href}"{attrs}>{html.escape(label)}</a>')
        position = match.end()
    output.append(linkify_text(text[position:]))
    return "".join(output)


def extract_title(markdown_text: str, fallback: str) -> str:
    for line in markdown_text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            return match.group(2).strip()
    return fallback


def render_markdown(markdown_text: str) -> str:
    output: list[str] = []
    paragraph: list[str] = []
    code_lines: list[str] = []
    in_code = False
    list_type: str | None = None

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{render_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()

        if FENCE_RE.match(line):
            flush_paragraph()
            close_list()
            if in_code:
                output.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(raw_line)
            continue

        if not line.strip():
            flush_paragraph()
            close_list()
            continue

        heading = HEADING_RE.match(line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            output.append(f"<h{level}>{render_inline(heading.group(2))}</h{level}>")
            continue

        unordered = LIST_RE.match(line)
        ordered = ORDERED_LIST_RE.match(line)
        if unordered or ordered:
            flush_paragraph()
            desired_type = "ul" if unordered else "ol"
            if list_type != desired_type:
                close_list()
                output.append(f"<{desired_type}>")
                list_type = desired_type
            item = (unordered or ordered).group(1)
            output.append(f"<li>{render_inline(item)}</li>")
            continue

        if line.lstrip().startswith("> "):
            flush_paragraph()
            close_list()
            output.append(f"<blockquote><p>{render_inline(line.lstrip()[2:])}</p></blockquote>")
            continue

        if re.fullmatch(r"\s*([-*_])(?:\s*\1){2,}\s*", line):
            flush_paragraph()
            close_list()
            output.append("<hr>")
            continue

        paragraph.append(line.strip())

    flush_paragraph()
    close_list()
    if in_code:
        output.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
    return "\n".join(output)


def relative_link(from_page: Path, to_page: Path) -> str:
    start = from_page.parent.as_posix() or "."
    return posixpath.relpath(to_page.as_posix(), start=start)


def page_template(*, title: str, body: str, output_relative: Path) -> str:
    css_href = relative_link(output_relative, Path("assets/style.css"))
    home_href = relative_link(output_relative, Path("index.html"))
    archive_href = relative_link(output_relative, Path("archive.html"))
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    full_title = SITE_TITLE if title == SITE_TITLE else f"{title} | {SITE_TITLE}"
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="RSSやAtomフィードから収集した記事情報のダイジェスト">
  <title>{html.escape(full_title)}</title>
  <link rel="stylesheet" href="{html.escape(css_href, quote=True)}">
</head>
<body>
  <header class="site-header">
    <div class="site-header__inner">
      <a class="brand" href="{html.escape(home_href, quote=True)}">{html.escape(SITE_TITLE)}</a>
      <nav aria-label="メインナビゲーション">
        <a href="{html.escape(home_href, quote=True)}">最新</a>
        <a href="{html.escape(archive_href, quote=True)}">過去ログ</a>
      </nav>
    </div>
  </header>
  <main>
    <article class="page">
{body}
    </article>
  </main>
  <footer class="site-footer">
    <div class="site-footer__inner">Generated from repository Markdown at {generated_at}</div>
  </footer>
</body>
</html>
"""


def markdown_output_path(markdown_path: Path) -> Path:
    relative = markdown_path.relative_to(ROOT).with_suffix(".html")
    return OUTPUT_DIR / relative


def build_markdown_pages(markdown_files: list[Path]) -> None:
    for markdown_path in markdown_files:
        text = markdown_path.read_text(encoding="utf-8")
        title = extract_title(text, markdown_path.stem)
        output_path = markdown_output_path(markdown_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_relative = output_path.relative_to(OUTPUT_DIR)
        output_path.write_text(
            page_template(title=title, body=render_markdown(text), output_relative=output_relative),
            encoding="utf-8",
        )


def build_archive(markdown_files: list[Path]) -> None:
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in markdown_files:
        relative = path.relative_to(DOCS_DIR)
        group = relative.parts[0] if relative.parts and DATE_DIR_RE.match(relative.parts[0]) else "その他"
        groups[group].append(path)

    sections: list[str] = ["<h1>過去ログ</h1>"]
    if not groups:
        sections.append('<p class="empty">公開できるMarkdownがまだありません。</p>')
    else:
        for group in sorted(groups, reverse=True):
            sections.append(f'<section class="archive-group"><h2>{html.escape(group)}</h2><ul>')
            for path in sorted(groups[group], key=lambda item: item.name):
                text = path.read_text(encoding="utf-8")
                title = extract_title(text, path.stem)
                output_relative = markdown_output_path(path).relative_to(OUTPUT_DIR)
                href = relative_link(Path("archive.html"), output_relative)
                sections.append(
                    f'<li><a href="{html.escape(href, quote=True)}">{html.escape(title)}</a> '
                    f'<span class="file-meta">({html.escape(path.name)})</span></li>'
                )
            sections.append("</ul></section>")

    (OUTPUT_DIR / "archive.html").write_text(
        page_template(title="過去ログ", body="\n".join(sections), output_relative=Path("archive.html")),
        encoding="utf-8",
    )


def latest_summary(markdown_files: list[Path]) -> Path | None:
    summaries = [path for path in markdown_files if path.name == "summary.md"]
    return max(summaries, key=lambda path: path.parent.name, default=None)


def build_index(markdown_files: list[Path]) -> None:
    preferred = ROOT / "today.md"
    source = preferred if preferred.exists() else latest_summary(markdown_files)
    if source is None:
        title = SITE_TITLE
        body = '<h1>情報収集ダイジェスト</h1><p class="empty">公開できる記事情報がまだありません。</p>'
    else:
        text = source.read_text(encoding="utf-8")
        title = extract_title(text, SITE_TITLE)
        body = render_markdown(text)

    (OUTPUT_DIR / "index.html").write_text(
        page_template(title=title, body=body, output_relative=Path("index.html")),
        encoding="utf-8",
    )


def build_404() -> None:
    body = '<h1>ページが見つかりません</h1><p><a href="index.html">最新記事へ戻る</a></p>'
    (OUTPUT_DIR / "404.html").write_text(
        page_template(title="404", body=body, output_relative=Path("404.html")),
        encoding="utf-8",
    )


def main() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    (OUTPUT_DIR / "assets").mkdir(parents=True)
    (OUTPUT_DIR / "assets/style.css").write_text(CSS + "\n", encoding="utf-8")
    (OUTPUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    markdown_files = sorted(DOCS_DIR.rglob("*.md")) if DOCS_DIR.exists() else []
    build_markdown_pages(markdown_files)
    build_index(markdown_files)
    build_archive(markdown_files)
    build_404()
    print(f"Built {len(markdown_files) + 3} HTML pages in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
