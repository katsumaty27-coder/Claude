# このリポジトリについて

Claude Code on the web から利用する、学習・調査用のワークスペースです。
（旧: ジョブカン勤怠自動入力ツールは別ツールで対応済みのため削除しました）

## 目的

調査テーマごとにファイルを作成し、Claude Code に学習・調査を回してもらうための置き場所です。
コードを書くプロジェクトではなく、基本は Markdown ベースのメモ・レポート置き場として運用します。

## ディレクトリ構成

```
research/
  README.md              調査テーマの一覧・インデックス
  <YYYY-MM-DD>_<topic>/  調査テーマごとのフォルダ
    notes.md              調査メモ・進行中の思考
    findings.md           結論・まとめ
    sources.md            参照リンク・出典
```

## 運用ルール

- 新しい調査を始めるときは `research/` 配下に `YYYY-MM-DD_topic-slug/` フォルダを作成する。
- フォルダ内のファイル名（notes / findings / sources）は固定。中身の構成はテーマに応じて柔軟でよい。
- 調査を追加・更新したら、必ず `research/README.md` の一覧も更新する。
- ルート直下に調査ファイルを直接置かない（`research/` 配下に集約する）。

## 今後コードを書く場合

npm / pip などの依存関係を持つプロジェクトを追加する場合は、
`.claude/hooks/session-start.sh` + `.claude/settings.json` の SessionStart hook を追加し、
Claude Code on the web のセッション起動時に依存関係が自動インストールされるようにする
（`session-start-hook` スキル参照）。現時点ではコード資産がないため未設定。
