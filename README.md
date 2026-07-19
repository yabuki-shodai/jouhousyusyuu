# jouhousyusyuu

[GitHub Pagesで収集結果を見る](https://yabuki-shodai.github.io/jouhousyusyuu/)

<!-- today-summary-link:start -->
[今日の記事サマリー（2026-07-20）](docs/2026-07-20/summary.md)
<!-- today-summary-link:end -->

RSS / Atom フィードから情報を収集し、日付ごとの Markdown ファイルとして保存するリポジトリです。

## 概要

このリポジトリでは、GitHub Actions を使って定期的にニュース・技術記事・企業技術ブログなどを収集します。

初期対象は以下です。

- Yahoo!ニュース
- Qiita
- Zenn

## ディレクトリ構成

```txt
.
├── config/
│   └── sources.json
├── scripts/
│   └── fetch_feeds.py
├── docs/
│   └── YYYY-MM-DD/
│       ├── yahoo.md
│       ├── qiita.md
│       └── zenn.md
└── .github/
    └── workflows/
        └── fetch-feeds.yml
```

## ローカル実行

```bash
python scripts/fetch_feeds.py
```

## 収集対象の追加

`config/sources.json` に RSS / Atom フィードを追加します。

```json
{
  "name": "example",
  "display_name": "Example Tech Blog",
  "type": "rss",
  "url": "https://example.com/feed.xml",
  "limit": 10,
  "category": "company_blog",
  "enabled": true
}
```

## 出力先

実行日の JST 日付で、以下のように保存します。

```txt
docs/YYYY-MM-DD/{source_name}.md
```

例:

```txt
docs/2026-07-08/qiita.md
```

## 方針

初期実装では、RSS / Atom で取得できる情報源のみを対象にします。
HTML スクレイピング、AI 要約、DB 保存、通知連携は後続拡張の対象です。

## 関連

- [作業の記録](https://github.com/users/yabuki-shodai/projects/5?pane=issue&itemId=210023191&issue=yabuki-shodai%7Clife-study%7C2)
