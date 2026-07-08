# jouhousyusyuu

RSS / Atom フィードや脆弱性情報を収集し、日付ごとの Markdown ファイルとして保存するリポジトリです。

## 概要

このリポジトリでは、GitHub Actions を使って定期的にニュース・技術記事・企業技術ブログなどを収集します。

初期対象は以下です。

- Yahoo!ニュース
- Qiita
- Zenn

追加機能として、CVE Digest による脆弱性情報サマリーも生成します。

CVE Digest は NVD と CISA KEV を取得し、関心技術に関連するCVE、CVSS 7.0以上、またはCISA KEV掲載の脆弱性を `summary.md` にまとめます。

## ディレクトリ構成

```txt
.
├── config/
│   ├── sources.json
│   └── cve-digest.json
├── scripts/
│   ├── fetch_feeds.py
│   └── cve_digest.py
├── docs/
│   ├── YYYY-MM-DD/
│   │   ├── yahoo.md
│   │   ├── qiita.md
│   │   └── zenn.md
│   └── cve-digest/
│       └── YYYY-MM-DD/
│           └── summary.md
└── .github/
    └── workflows/
        ├── fetch-feeds.yml
        └── cve-digest.yml
```

## ローカル実行

RSS / Atom 収集:

```bash
python scripts/fetch_feeds.py
```

CVE Digest:

```bash
python scripts/cve_digest.py
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

CVE Digest の監視キーワードは `config/cve-digest.json` の `watch_keywords` で管理します。

## 出力先

RSS / Atom は実行日の JST 日付で、以下のように保存します。

```txt
docs/YYYY-MM-DD/{source_name}.md
```

例:

```txt
docs/2026-07-08/qiita.md
```

CVE Digest は以下に `summary.md` だけを保存します。

```txt
docs/cve-digest/YYYY-MM-DD/summary.md
```

## 方針

初期実装では、RSS / Atom で取得できる情報源のみを対象にします。
HTML スクレイピング、AI 要約、DB 保存、通知連携は後続拡張の対象です。

CVE Digest は外部APIが一部失敗しても、取得できた範囲で `summary.md` を生成します。

## 関連

- [作業の記録](https://github.com/users/yabuki-shodai/projects/5?pane=issue&itemId=210023191&issue=yabuki-shodai%7Clife-study%7C2)
