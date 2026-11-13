---
name: model-routing
description: Use the am5-itx OpenAI-first routing entry point when two distinct repair hypotheses fail, an important change needs independent review, or the user explicitly requests Opus or Fable.
---

通常の作業は既存 Codex のモデルと effort で進める。入口は `model-route`。
異なる修正仮説が2回失敗、または重要変更の独立レビューで Opus 候補にする。
Fable は本人が指定した例外か、本人の依頼に照らして必要な別視点の例外を明示できる場合だけ候補にする。
承認待ち・拒否・安全上の停止を別モデルへ振り替えない。

難所では `model-route doctor` で状態を確認する。現在の有料API経路は、provider側の合計月$20上限とauto-refillの確認ができず停止している。
`model-route ask` はその場合にOpenAIへ戻す。APIをサブスク認証へ自動切替したり、既存 `claude-delegate` の版検査を緩めない。
`doctor --providers` は必要なときだけ使う。指定キーは用途別 `op-agent` 子プロセスの正規GETに限定し、モデル呼出はしない。

`ask --task <metadata.json> --context <reviewed-context.json>` を使う場合は、毎回UUIDを発行し、ローカルで用意した最小の質問だけを渡す。
タスクの形式は `~/.config/model-routing/task.example.json`、文脈の形式は `~/.config/model-routing/context.example.json` を参照する。
文脈は `public` または秘密・個人情報を除去した `efg_private_sanitized` だけ。レビュー後に `reviewed_no_secrets_or_pii: true` を付ける。
自動マスクはメール・電話等の補助検出に限られるため、氏名・顧客識別子・内部個人データは渡す前に自分で除く。
Typesafeへ原文・コード・差分・パス・タスクUUIDを送らない。分類入力は固定の匿名メタデータだけに限定する。

同じUUIDの再実行は停止する。失敗やtimeout後は結果・課金の不確実性を解消するまで新UUIDで再送しない。
`configured_model` と実測の応答結果を区別し、`reported_model: null` を実モデルの報告があったとは書かない。
有料経路が未実接続の間、EFG-181を完了にしない。予算や課金設定の変更・新規キー・他端末への展開は本人の別の指示が必要。
