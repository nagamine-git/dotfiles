# グローバル運用ルール (全プロジェクト共通)

## モデル配車則 (2026-07-03 制定 / 2026-07-26 改定: Opus 5 リリースに伴う — Fable 週次枠の焼き尽くし防止)

- メインループのデフォルトは `default` (= Max では Opus 5) / effort high。Fable 5 は Opus/Sonnet で届かない最難関セッション専用 (`/model fable` で都度切替。週次プールの最大50%まで・追加枠なし・/fast 不可)
- Fable セッション中に週次枠 >80% なら Opus (fast) に自主降格
- `Agent` / `Workflow` の subagent は**必ず model を明示**する:
  実装・調査 = `sonnet` / 設計トレードオフ・レビュー判定 = `opus` / 機械的一括処理 = `haiku`
- max レビュー艦隊 (多 agent workflow) はセキュリティ境界・大型・危険変更のみ。通常 PR はメインループの inline レビュー + CI で足りる
