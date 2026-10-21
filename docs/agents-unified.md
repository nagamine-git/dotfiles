# Claude Code と Codex の共通設定

どのリポジトリでも、リポジトリ側にファイルを足さずに Claude Code と Codex が同じ指示・スキル・MCP を使えるようにする。
正本はこの dotfiles (chezmoi)。`~` 側は直接編集せず、ここを直して `chezmoi apply` する。

## 共有しているもの

| 項目 | 正本 (このリポジトリ) | Claude Code | Codex |
|---|---|---|---|
| グローバル指示 | `dot_agents/AGENTS.md` → `~/.agents/AGENTS.md` | `~/.claude/CLAUDE.md` が `@~/.agents/AGENTS.md` を読み込む | `~/.codex/AGENTS.md` (`private_dot_codex/AGENTS.md.tmpl` が同じ内容を出す) |
| リポジトリの指示 | 各 repo の `AGENTS.md` / `CLAUDE.md` | v2.1.277 以降は `AGENTS.md` を標準で読む。`settings.json` の `pluginConfigs` で `CLAUDE.md` と両方読む | `config.toml` の `project_doc_fallback_filenames` に `CLAUDE.md` (`modify_private_config.toml` が保つ) |
| スキル | `dot_agents/skills/<name>/` → `~/.agents/skills/` | `~/.claude/skills/<name>` が上へのシンボリックリンク | `~/.agents/skills` を直接読む |
| MCP サーバー | `dot_agents/mcp.json` | `claude mcp add-json -s user` で `~/.claude.json` へ | `codex mcp add` で `config.toml` へ |
| subagent | `dot_claude/agents/*.md` | そのまま | `~/.codex/agents/*.toml` を生成 (モデルは指定せず effort だけ写す) |
| メモリ | Claude の自動メモリ `~/.claude/projects/<repo>/memory/` | 自動で読み書き | `agent-memory-dir` で場所を知り、指示どおり読み書き |
| 引き継ぎ | Linear のチケット / PR | 同左 | 同左 (セッションは共有されない) |

反映は `run_onchange_after_agents-sync.sh.tmpl` が `agents-sync all` を呼ぶ。mcp.json・スキル名・subagent の md が変わったときだけ走る。
手で走らせるなら `agents-sync all [--dry-run]`。何度実行しても同じ結果で、消すのは中身が同一の複製だけ。

## 追加のしかた (1 回書けば両方に入る)

- スキル: `dot_agents/skills/<name>/SKILL.md` を作って `chezmoi apply`。`npx skills add` で `~/.agents/skills` に入れたものも `agents-sync skills` が Claude 側にリンクする。
- MCP サーバー: `dot_agents/mcp.json` に名前・`command` / `args` または `type: http` と `url` を足して `chezmoi apply`。秘密の環境変数は `secrets` に名前だけ書く (値は書かない。自動では足されないので `claude mcp add -e` / `codex mcp add --env` で 1 回入れる)。
- subagent: `dot_claude/agents/<name>.md` を書く。Codex 用 toml は自動生成。
- 指示: `dot_agents/AGENTS.md` を直す。道具固有の規則は「Claude Code のみ」「Codex のみ」の節に書く。

## 日本語の回答と ChatGPT / dot

回答の書き方は `dot_agents/AGENTS.md` の共通節が正本。文字数の固定上限は設けず、自然な文と必要な説明を優先する。
ChatGPT の Settings > Personalization にある ChatGPT / Codex の custom instructions は、`agents-sync` の同期対象ではない。「回答の書き方」の本文を両方へ反映し、保存後に開き直して確認する。
dot の Custom rules に同じ文字数制限を重ねない。書き方は custom instructions、行動の許可は Custom rules に分ける。
この設定は生成時の指針であり、実際の読みやすさは新しい会話でも確認する。既存会話には古い指示やメモリが残ることがある。

## 公式の仕様 (確認した内容)

- Claude Code は `AGENTS.md` を標準で読む (v2.1.277 以降)。ただし `CLAUDE.md` がある repo では `CLAUDE.md` だけ。`@path` の読み込みは `~/.claude/CLAUDE.md` から `@~/...` も可 (ユーザー設定なので承認ダイアログなし)。ブロックの HTML コメントは読み込み時に除かれる。<https://code.claude.com/docs/en/memory>
- Claude Code のスキルは `~/.claude/skills/<name>/SKILL.md`。シンボリックリンクも読む。<https://code.claude.com/docs/en/skills>
- Claude Code の MCP はユーザースコープが `~/.claude.json`。`settings.json` に `mcpServers` を書く方法は文書にない。<https://code.claude.com/docs/en/mcp>
- Codex は各ディレクトリで `AGENTS.override.md` → `AGENTS.md` → `project_doc_fallback_filenames` の順に 1 つだけ読む。グローバルは `~/.codex/AGENTS.md`。上限 `project_doc_max_bytes` は既定 32KiB。<https://learn.chatgpt.com/docs/agent-configuration/agents-md>
- Codex のスキルは `~/.agents/skills` (ユーザー) と repo の `.agents/skills`。シンボリックリンクも辿る。`name` と `description` が必須。<https://learn.chatgpt.com/docs/build-skills>
- Codex の MCP は `config.toml` の `[mcp_servers.<name>]`。stdio は `command` / `args` / `env`、HTTP は `url`。OAuth は `codex mcp login <name>`。<https://learn.chatgpt.com/docs/extend/mcp>
- Codex の subagent は `~/.codex/agents/*.toml` (`name` / `description` / `developer_instructions` が必須)。`sandbox_mode` と `mcp_servers` は上書きできない。<https://learn.chatgpt.com/docs/agent-configuration/subagents>

## 共有できないもの

- 認証: MCP の OAuth は道具ごとに 1 回ずつ。Codex は `codex mcp login <name>`、Claude Code は `/mcp`。API キーなどの秘密は各道具の設定に残っている (dotfiles には置かない)。
- フック・権限・サンドボックス・モデル・effort: 形式も意味も違う。`~/.claude/hooks` と `~/.codex/hooks` は別々の複製。Codex のフックは内容のハッシュを本人が信頼登録する。
- スラッシュコマンド (`~/.claude/commands`): Claude Code だけ。Codex のデスクトップ取り込みはスキル (`source-command-*`) に変換するが、`agents-sync` は Claude に戻さない。
- subagent の `disallowedTools` (読み取り専用の強制): Codex に対応する設定がない。Codex 側は本文の指示だけが頼り。
- repo の `CLAUDE.md` 内の `@` 読み込み: Codex は展開しない。さらに repo に `AGENTS.md` と `CLAUDE.md` の両方があると Codex は `AGENTS.md` だけを読む。repo 側は `CLAUDE.md` の先頭を `@AGENTS.md` にして中身を `AGENTS.md` に集める (リポジトリごとの作業)。
- 指示中の HTML コメント: Claude Code は除くが Codex は読む。`<!-- 要確認 -->` は Codex の文脈に残る。
- スキル `freee-monthly`: Claude 側と Codex 側が意図的に別内容 (Codex 版に Chrome 手順などの追記がある)。どちらも残してあり、統合は未決。

## 注意: Codex デスクトップの自動取り込み

Codex のデスクトップアプリは Claude Code の設定 (settings.json・スキル・コマンド・subagent・フック・MCP) を起動時に Codex へ取り込む設定になっている (Settings > Import)。
取り込みはコピーで、元と食い違いうる (dev-radar の本文が書き換わっていた)。既存ファイルは上書きしない挙動に見えるが、公式文書は明記していない。
この仕組みでは共通化できないので、ここでは共通の置き場から生成・リンクする方式にした。取り込みを切るかどうかは本人の判断 (未変更)。

## 確認コマンド

```sh
agents-sync all --dry-run                 # 何を直すか
claude mcp list; codex mcp list           # 同じ名前が並ぶ (Codex 側の内蔵・プラグイン分は別)
codex debug prompt-input hello            # Codex が読む指示・スキルの一覧 (モデル呼び出しなし)
agent-memory-dir                          # 今の repo の Claude メモリの場所
python3 tests/agents-sync.py              # 他に tests/agent-memory-dir.py, tests/codex-config.py
```

## Slack から am5-itx の Claude Code に依頼する bot

`dot_local/bin/executable_slack-claude` (`~/.local/bin/slack-claude`)。Socket Mode で常駐し、本人 (user `U03L2HM8Q4X` かつ team `T03LKHSP0TW`) の発言だけを `claude -p` に渡して、結果をスレッドに返す。それ以外の人・bot・編集や削除などの subtype 付きは黙って無視する。

- 反応するもの: DM は全部。複数人 DM とチャンネルは、bot へのメンションか、bot が既に会話しているスレッド内の発言。受け付けたら元の発言に :eyes:、終われば :white_check_mark:、失敗は :x: とエラーの要約。
- スレッドごとに Claude のセッションを持つ (`~/.local/state/slack-claude/sessions.json`)。同じスレッドは到着順に 1 つずつ、別スレッドは並列。
- 権限・モデルは上書きしない (`agent-gateway` と同じく `~/.claude/settings.json` に従う)。`-p` では承認を答える人がいないので `--permission-prompts none` で、確認が要る操作は拒否になる。
- 作業ディレクトリは既定 `$HOME` (`SLACK_CLAUDE_CWD`)、タイムアウトは既定 30 分 (`SLACK_CLAUDE_TIMEOUT_SEC`)。claude には `SLACK_*` と `OP_SERVICE_ACCOUNT_TOKEN` を渡さない (secrets.env の他の値は渡る)。
- 鍵: 1Password の vault 'Agents' に `SLACK_APP_TOKEN` (`xapp-`、scope `connections:write`) と `SLACK_BOT_TOKEN` (`xoxb-`) を入れ、専用の `~/.config/agents/slack.env` に `op://Agents/...` の参照を足す。値は書かない。登録・確認手順は [agent-secrets.md](agent-secrets.md)。
- Slack app: Socket Mode を有効にし、Event Subscriptions に `app_mention` `message.channels` `message.groups` `message.im` `message.mpim`、Bot scope に `app_mentions:read` `channels:history` `groups:history` `im:history` `mpim:history` `chat:write` `reactions:write` `im:write`。
- サービス: `private_dot_config/systemd/user/slack-claude.service.tmpl`。am5-itx 以外では `.chezmoiignore` で外す。鍵を入れて `chezmoi apply` した後に 1 回だけ起動する。

```sh
systemctl --user enable --now slack-claude
op-agent run --env-file ~/.config/agents/slack.env -- slack-claude dm "通知テスト"     # 本人に DM が 1 通届く
python3 tests/slack-claude.py                                                          # ネットワークも claude も呼ばない
```
