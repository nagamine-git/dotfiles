# エージェントが使う 1Password の秘密

Vault が空でも、困っていないサービスの鍵を先に集める必要はない。
実行したい作業が認証で止まったら、その作業に必要な鍵だけを追加する。
Personal などの既存 Vault を一括で移したり、エージェントの読取範囲を広げたりしない。

## 認証の分担

| 用途 | 管理する場所 |
|---|---|
| ChatGPT / Codex / Claude の接続アプリ、MCP の OAuth | 各ツールの接続設定。Google / GitHub 等の認証情報を Vault にコピーしない |
| CLI や常駐サービスに必要な API キー | 1Password の `Agents` Vault |
| 環境変数と秘密の対応 | chezmoi の `private_dot_config/agents/private_*.env`。`op://Agents/...` の参照だけを書く |
| 1Password service account のトークン | ホストごとの `~/.config/op/agents-sa-token`。chezmoi 管理外 |

`op-agent` は service account で 1Password CLI を呼ぶ。
現在の service account は `Agents` の読取専用なので、秘密の登録や発行はできない。
外部サービスのキーも、発行元で本人が作成する必要がある。
権限を追加する前に、既存の OAuth 接続で作業できるか確認する。

## 値を表示せずに確認する

```sh
agent-secrets-check
agent-secrets-check --env-file ~/.config/agents/slack.env
agent-secrets-check --env-file ~/.config/agents/slack.env --resolve
```

既定ではアカウントの種類、見える Vault 名と `Agents` の項目数、参照の環境変数名を表示する。
項目名、フィールド、秘密の値は表示せず、参照の値も解決しない。
`--resolve` を付けたときだけ `op-agent run` で読み、各変数の `present` / `absent` を返す。
エラー時も CLI の応答本文は表示しない。
終了コードは成功が `0`、失敗が `1`。参照がないファイルは `--resolve` では失敗になる。

この確認は `Agents` だけを見られる service account と、リテラルの秘密参照を前提にする。
参照は `op://Agents/item/field` または `op://Agents/item/section/field` とし、空白を含む名前は引用符で囲む。
変数の展開やクエリ付き参照は扱わない。
Vault の項目数が増えても、必要な変数が揃ったとは限らない。
`present` は値が空でないことだけを示し、API の認証成功や権限までは確認しない。

## 認証で作業が止まったとき

1. エージェントは、止まったコマンドと不足する変数名、必要な権限を示す。
2. 本人が発行元で用途に合うキーを作り、`Agents` に保存する。値はチャットに貼らない。
3. 用途別の env ファイルへ、実際の item / field 名で参照を追加する。推測した参照を有効にしない。
4. `chezmoi diff` と dry-run を確認し、参照を反映する。`agent-secrets-check --env-file ... --resolve` で解決を確認する。
5. そのファイルを指定して必要なコマンドを実行し、実際の認証と権限を確認する。

```sh
op-agent run --env-file ~/.config/agents/<用途>.env -- <必要なコマンド>
```

`secrets.env` は常駐サービスへまとめて渡さない。
`slack.env` のような用途別ファイルで、プロセスに渡す鍵を絞る。
`op run` の出力マスキングは補助であり、全ての表示形式を隠せる保証はない。
`env`、デバッグ出力、キーを表示する API を使って確認しない。

## Slack bot を使えるようにする

Slack bot は現在、`SLACK_APP_TOKEN` と `SLACK_BOT_TOKEN` の登録待ち。
2026-10-21 の確認時点で unit は `disabled` / `inactive` だった。
`slack.env` はコメントだけの雛形なので、まだ起動できる状態ではない。

現在の bot 構成の設定は [agents-unified.md](agents-unified.md#slack-から-am5-itx-の-claude-code-に依頼する-bot) にある。
Slack app で Socket Mode を有効にし、次を揃える。

| 保存する変数 | 発行するトークンと権限 |
|---|---|
| `SLACK_APP_TOKEN` | App-Level Token (`xapp-`)、`connections:write` |
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-`)。Bot scope: `app_mentions:read` `channels:history` `groups:history` `im:history` `mpim:history` `chat:write` `reactions:write` `im:write` |

Event Subscriptions は `app_mention` `message.channels` `message.groups` `message.im` `message.mpim`。
トークンは `Agents` の別々の項目に保存し、`slack.env` のコメント例を実際の参照に置き換える。
`Slack app` / `Slack bot` / `credential` は例なので、既存項目があるとは扱わない。

参照の反映と解決ができてから、本人がサービスを起動する。
この確認作業では起動・再起動しない。

```sh
agent-secrets-check --env-file ~/.config/agents/slack.env --resolve
systemctl --user daemon-reload
systemctl --user enable --now slack-claude
```

起動後は `systemctl --user is-active slack-claude` と実際の Slack 応答で確認する。
参照の解決だけでは、Socket Mode 接続や bot の動作を確認したことにはならない。
