# ニュース速報

> Daily multi-category news updates powered by GitHub Actions and AI.

[![LED Board](https://led-borad-svg.vercel.app/api/led-board?text=%E3%83%8B%E3%83%A5%E3%83%BC%E3%82%B9%E9%80%9F%E5%A0%B1&duration=11)](today.md)

ニュース速報は、RSS / Atom フィードから幅広いジャンルのニュースを毎日収集し、ジャンル別に整理・選定して保存するプロジェクトです。

## ✨ Features

### 📰 Multi-category News

政治・国際・経済・サイバーセキュリティ・IT・科学・アニメ・歴史など、特定分野に偏らず幅広いニュースを収集します。

#### Sources

- Yahoo!ニュースのピックアップ
- Googleニュースのテーマ別検索 RSS

#### Categories

- 総合
- 政治
- 国際・外交
- 経済・ビジネス
- サイバーセキュリティ / ハッキング
- IT・AI
- 科学・宇宙
- 医療・健康
- アニメ・漫画
- 歴史・考古
- 教育
- 社会・事件
- スポーツ
- 文化・芸術・映画・音楽

---

### 🎯 Daily Selection

毎日の「今日見る候補」を最大 20 件まで選定します。

#### Selection Policy

- 最大 20 件
- 同一ジャンルは原則 2 件まで
- 記事が十分にある場合は 8 ジャンル以上を優先
- 同じ話題や同じ媒体への偏りを抑制
- 技術分野だけを特別扱いせず、複数ジャンルへ分散
- Gemini が利用できない場合もジャンル分散ルールでフォールバック

---

### 🤖 AI Summary

Gemini API を利用して、収集した記事から読む候補を選定します。

Gemini API が利用できない場合でも、フォールバック処理によりジャンルを分散した候補を生成します。

利用する場合は環境変数 `GEMINI_API_KEY` を設定してください。GitHub Actions ではリポジトリシークレットに設定します。

---

## 📋 Dashboard

最新の収集結果は以下から確認できます。

- 📊 [`today.md`](today.md)

<!-- today-summary-link:start -->
[今日の記事サマリー（2026-09-05）](docs/2026-09-05/summary.md)
<!-- today-summary-link:end -->

---

## 📁 Outputs

実行日の JST 日付で、取得元ごとの記事一覧とサマリーを保存します。

```text
today.md

docs/
└── YYYY-MM-DD/
    ├── summary.md
    └── {source_name}.md
```

---

## ⚙️ GitHub Actions

ニュース収集は GitHub Actions から自動実行します。

| Workflow | Description |
|----------|-------------|
| `fetch-feeds.yml` | RSS / Atom の取得・記事整理・今日見る候補の生成 |

---

## ⚙️ Configuration

収集元や記事選定ルールは設定ファイルから変更できます。

```text
config/
├── sources.json
└── preferences.json
```

### `config/sources.json`

RSS / Atom フィードの追加・変更を行います。

```json
{
  "name": "example_news",
  "display_name": "Example News",
  "type": "rss",
  "url": "https://example.com/feed.xml",
  "limit": 15,
  "category": "world",
  "enabled": true
}
```

### `config/preferences.json`

以下のような記事選定ルールを変更できます。

- 興味キーワード
- 選定件数
- ジャンルごとの上限

---

## 🛠️ Local Development

```bash
python scripts/fetch_feeds.py
python scripts/group_new_articles.py
```

Gemini を利用する場合は `GEMINI_API_KEY` を環境変数に設定してください。

---

## 📁 Structure

```text
.
├── .github/
│   └── workflows/
│       └── fetch-feeds.yml
├── config/
│   ├── sources.json
│   └── preferences.json
├── data/
├── docs/
│   └── YYYY-MM-DD/
├── scripts/
│   ├── fetch_feeds.py
│   └── group_new_articles.py
├── README.md
└── today.md
```

---

## License

This project is licensed under the [MIT License](LICENSE).
