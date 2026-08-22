# jouhousyusyuu

[GitHub Pagesで収集結果を見る](https://yabuki-shodai.github.io/jouhousyusyuu/)

<!-- today-summary-link:start -->
[今日の記事サマリー（2026-08-23）](docs/2026-08-23/summary.md)
<!-- today-summary-link:end -->

RSS / Atom フィードから幅広いニュースを収集し、日付ごとの Markdown ファイルとして保存するリポジトリです。

## 収集方針

企業ブログ、Qiita、Zenn などの技術ブログ・投稿サイトは収集対象から外し、ニュース記事を中心に収集します。

現在の主なジャンルは以下です。

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

収集元は Yahoo!ニュースのピックアップと、Googleニュースのテーマ別検索 RSS を利用します。

## 記事選定

毎日の「今日見る候補」は、技術分野を特別扱いせず、複数ジャンルに分散するよう選定します。

- 最大 20 件
- 同一ジャンルは原則 2 件まで
- 記事が十分にある場合は 8 ジャンル以上を優先
- 同じ話題や同じ媒体への偏りを避ける
- Gemini が利用できない場合も、同じジャンル分散ルールでフォールバック選定する
- 新規記事一覧はジャンル別に見出しを分けて表示する

## ディレクトリ構成

```txt
.
├── config/
│   ├── sources.json
│   └── preferences.json
├── scripts/
│   ├── fetch_feeds.py
│   └── group_new_articles.py
├── data/
├── docs/
│   └── YYYY-MM-DD/
└── .github/
    └── workflows/
        └── fetch-feeds.yml
```

## ローカル実行

```bash
python scripts/fetch_feeds.py
python scripts/group_new_articles.py
```

Gemini による記事選定を利用する場合は `GEMINI_API_KEY` を環境変数に設定します。未設定の場合はジャンル分散フォールバックで選定します。

## 収集対象の変更

`config/sources.json` に RSS / Atom フィードを追加・編集します。

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

興味キーワードや選定件数、ジャンルごとの上限は `config/preferences.json` で変更できます。

## 出力先

実行日の JST 日付で、取得元ごとの記事一覧とサマリーを保存します。

```txt
docs/YYYY-MM-DD/{source_name}.md
docs/YYYY-MM-DD/summary.md
today.md
```

## 関連

- [作業の記録](https://github.com/users/yabuki-shodai/projects/5?pane=issue&itemId=210023191&issue=yabuki-shodai%7Clife-study%7C2)
