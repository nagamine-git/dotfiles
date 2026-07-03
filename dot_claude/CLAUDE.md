# グローバル運用ルール (全プロジェクト共通)

## モデル配車則 (2026-07-03 制定 — Fable 週次枠の焼き尽くし防止)

- Fable はメインループ (司令塔の判断・裁定) 専用。Fable 週次枠 >80% なら Opus (fast) に自主降格
- `Agent` / `Workflow` の subagent は**必ず model を明示**する:
  実装・調査 = `sonnet` / 設計トレードオフ・レビュー判定 = `opus` / 機械的一括処理 = `haiku`
- max レビュー艦隊 (多 agent workflow) はセキュリティ境界・大型・危険変更のみ。通常 PR はメインループの inline レビュー + CI で足りる
