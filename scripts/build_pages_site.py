from __future__ import annotations

import argparse
import html
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import markdown

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT_DIR / "docs"
DEFAULT_DESTINATION = ROOT_DIR / "_site"
MARKDOWN_LINK_PATTERN = re.compile(r'href="([^"]+)"')
HEADING_PATTERN = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the GitHub Pages static site.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    return parser.parse_args()


def extract_title(markdown_text: str, fallback: str) -> str:
    match = HEADING_PATTERN.search(markdown_text)
    return match.group(1).strip() if match else fallback


def rewrite_local_markdown_links(rendered_html: str) -> str:
    def replace(match: re.Match[str]) -> str:
        href = html.unescape(match.group(1))
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or not parsed.path.lower().endswith(".md"):
            return match.group(0)

        rewritten_path = f"{parsed.path[:-3]}.html"
        rewritten = urlunsplit((parsed.scheme, parsed.netloc, rewritten_path, parsed.query, parsed.fragment))
        return f'href="{html.escape(rewritten, quote=True)}"'

    return MARKDOWN_LINK_PATTERN.sub(replace, rendered_html)


def relative_url(from_file: Path, target: Path) -> str:
    return Path(os.path.relpath(target, start=from_file.parent)).as_posix()


def render_document(markdown_text: str, title: str, output_path: Path, destination: Path) -> str:
    body = markdown.markdown(
        markdown_text,
        extensions=["extra", "sane_lists", "toc"],
        extension_configs={"toc": {"permalink": True}},
        output_format="html5",
    )
    body = rewrite_local_markdown_links(body)

    stylesheet = relative_url(output_path, destination / "assets" / "style.css")
    home = relative_url(output_path, destination / "index.html")
    safe_title = html.escape(title)

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <meta name="description" content="ニュース・技術記事・脆弱性情報の自動収集ダイジェスト">
  <title>{safe_title} | 情報収集ダイジェスト</title>
  <link rel="stylesheet" href="{stylesheet}">
</head>
<body>
  <header class="site-header">
    <div class="site-header__inner">
      <a class="site-title" href="{home}">情報収集ダイジェスト</a>
      <a class="repository-link" href="https://github.com/yabuki-shodai/jouhousyusyuu">GitHub</a>
    </div>
  </header>
  <main class="content">
    <article class="article">
{body}
    </article>
  </main>
  <footer class="site-footer">GitHub Actions により自動更新</footer>
  <script>
    document.querySelectorAll('a[href^="http"]').forEach((link) => {{
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
    }});
  </script>
</body>
</html>
"""


def build_site(source: Path, destination: Path) -> int:
    source = source.resolve()
    destination = destination.resolve()

    if not source.exists():
        raise FileNotFoundError(f"source directory not found: {source}")
    if not (source / "index.md").exists():
        raise FileNotFoundError(f"index.md not found: {source / 'index.md'}")

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    page_count = 0
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        output_path = destination / relative

        if path.is_dir():
            output_path.mkdir(parents=True, exist_ok=True)
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".md":
            output_path = output_path.with_suffix(".html")
            markdown_text = path.read_text(encoding="utf-8")
            title = extract_title(markdown_text, path.stem)
            output_path.write_text(
                render_document(markdown_text, title, output_path, destination),
                encoding="utf-8",
            )
            page_count += 1
        else:
            shutil.copy2(path, output_path)

    (destination / ".nojekyll").write_text("", encoding="utf-8")
    print(f"built {page_count} pages: {destination.relative_to(ROOT_DIR)}")
    return page_count


def main() -> int:
    args = parse_args()
    build_site(args.source, args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
