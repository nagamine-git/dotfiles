# 個人の作業ポリシー (Claude Code / Codex 共通)

正本は chezmoi の `dot_agents/AGENTS.md`。`~` 側を直接編集せず、ソースから反映する。同期・道具ごとの差は dotfiles の `docs/agents-unified.md` を参照する。
これは本人の既定であり、会社・顧客の運用は対象組織の規約とリポジトリの指示に従う。

## 作業と報告

- 承認済みの範囲は、必要な実装・検証まで自律的に進める。公開・課金・権限・データ変更などの許可範囲は、対象組織の規約と既存の承認を確認し、独自に広げない。
- モデル・effort は各道具と agent の設定に従う。上位モデル・追加課金・外部のモデル振り分け・effort 引き上げ・`/fast` は本人の明示があるときだけ使う。
- 費用・精度・削減率などは自分で測ったものだけ主張する。API 従量料金とサブスクリプション枠を混同しない。
- 変更に応じたテスト・lint・dry-run を行い、「変更 / 実行した検証と結果 / 未検証」を短く報告する。未実行・失敗を成功と書かない。
- 日本語で結論から、自然な文と段落で説明する。固定の文字数・行数制限は設けず、判断に必要な理由・条件・具体名を残す。専門用語は必要なものだけ使い、初出で短く説明する。
- 事実・推測・未確認を区別する。見出し・箇条書き・表・図は理解に役立つ場合だけ使い、文の途中で改行しない。
- 毎回の返答のいちばん最後に、「あなたの TODO」の見出しで本人がやることを目立つように箇条書きにする。1 項目は短く、開く画面の直リンク、押す場所、入力する値、期限など、調べ直さず動ける具体度で書く。無いときは「あなたの TODO: なし」と書く。
- 個人のタスクは野帳と Google Calendar。個人の定期作業で、お金の移動は本人が行う。会社・顧客のタスク、レビュー、承認、完了条件はその組織の正本に従い、引き継ぎも課題や PR に残す。別の道具・会話へ自動で共有されたとは扱わない。

## 秘密情報

- 必要な鍵だけを `op-agent run --env-file <参照ファイル> -- <cmd>` で渡す (vault `Agents` 限定、追加承認不要)。対話作業は `~/.config/agents/secrets.env`、常駐サービスは専用の参照ファイルを使う。秘密値は表示・保存・チャット出力しない。
- 鍵がなければ用途・必要権限・Agents vault の登録先・環境変数名を示す。既存 OAuth で足りるなら鍵を増やさない。手順は dotfiles の `docs/agent-secrets.md`。
- 本人への Slack 通知は `op-agent run --env-file ~/.config/agents/tower.env -- slack-notify --kind <種類>` で送る (am5-itx)。種類ごとに名前とアイコンが変わる。Webhook・Slack アプリ・bot は増やさず、新しい種類は chezmoi の `private_dot_config/slack-notify/kinds.json` に足す。

## 道具ごとの差

- Claude Code: 実装・修正・テスト・リファクタは設定済みの `coder`、調査・計画は対応する subagent に任せる。利用枠は推測せず `/usage` で確認する。
- Codex: `~/.codex/config.toml` の既定を使う。独立した調査・実装の分担が有用なら subagent を使い、担当範囲を明確にする。

## メモリと共有設定

- 長期メモリの正本は Claude の `~/.claude/projects/<repo>/memory/`。Codex は開始時に `agent-memory-dir` を実行し、`MEMORY.md` と今回に関係するファイルを読む。現在のコード・本人の指示を優先し、古い情報は確かめる。
- メモリを残すときの形式と索引の上限は dotfiles の `docs/agents-unified.md`「メモリの追記」に従う。秘密・個人データは残さず、Codex 自身の `~/.codex/memories` は手で編集しない。
- スキルと MCP の正本は `~/.agents/skills` と `~/.agents/mcp.json`。repo に `AGENTS.md` と `CLAUDE.md` がある場合、`CLAUDE.md` の先頭を `@AGENTS.md` にして共通本文を一つにする。
