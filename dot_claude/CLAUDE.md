# グローバル運用ルール (全プロジェクト共通)

- モデルと effort は既定 (Opus 5.5 / medium) のまま使う。subagent は `~/.claude/agents` で effort low。コードを書く作業 (実装・修正・テスト・リファクタ) は `coder` subagent (Sonnet 5.5 xhigh) に任せる。high 以上はユーザーが `/effort` で上げたときだけ。Fable 5.1、/fast、追加課金、外部のモデル振り分けサービスはユーザーが明示したときだけ使い、subagent の model にも指定しない。利用枠は推測せず `/usage` で確認する。
- 削減率・精度・「ミスゼロ」などの数値は自分で測ったものだけ主張する。API の従量料金とサブスクリプション枠は別物。
- 完了報告は「変更 / 実行した検証とその結果 / 未検証」を短く書く。
- 秘密が要るコマンドは承認なしで `op-agent run --env-file ~/.config/agents/secrets.env -- <cmd>` で実行する (vault 'Agents' 限定)。無い秘密は本人に Agents vault への追加と secrets.env への参照追加を頼む。値は表示・保存・チャット出力しない。
