# Claude Code・Codex・Pi の共通設定

どのリポジトリでも、リポジトリ側にファイルを足さずに Claude Code・Codex・Pi が同じ指示・スキル・MCP を使えるようにする。
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

## Pi (am5-itx だけ。Claude Code と Codex をまとめて扱う主入口)

グローバル指示は `~/.pi/agent/AGENTS.md` で、`dot_pi/agent/AGENTS.md.tmpl` が Codex と同じく `dot_agents/AGENTS.md` の内容を出す。
スキルは Pi が `~/.agents/skills` を標準で読むのでリンクは要らない。メモリは Codex と同じく `agent-memory-dir` で場所を知って読む。

- モデル: 既定 (default)・ここぞ (peak)・軽量 (light) の 3 段を `.chezmoidata/pi.yaml` に置き、`dot_pi/agent/modify_settings.json` (modify-template) が `~/.pi/agent/settings.json` の `defaultProvider` / `defaultModel` / `defaultThinkingLevel` (default 段)・`modelThinkingLevels` (3 段の `provider/id`)・`enabledModels` (Ctrl+P の順。`provider/id:thinking` で、切り替えると thinking も変わる) だけを上書きする。Pi が書くほかのキー (`lastChangelogVersion`・`deviceId` など) と `modelThinkingLevels` のほかの項目は残す。段の値はクラウドの model-radar が PR で直す。
- MCP: `agents-sync mcp` が `~/.pi/agent/mcp.json` を直接書く (Pi に add-json が無いため)。共有の定義から作るのは `command` / `args` / `url` だけで、`type`・`secrets`・`clients` は書かない。`enabled`・`exposure`・`toolExposure`・`description`・`oauth`・`env`・`headers` など本人や `/mcp` が足したキーと、`pi mcp add` で入れた Pi だけの定義は残す (後者は「Pi だけにある」と報告)。変更があるときだけ一時ファイルから置き換える。OAuth は `pi mcp login <name>` で 1 回ずつ (トークンは `~/.pi/agent/mcp-auth.json`)。
- subagent: `extensions/subagent.ts` が、動いている Pi の同梱例 `examples/extensions/subagent/index.ts` (`getExamplesPath()` の下) を読み込むだけの口で、写しは持たない。Pi を更新すると例も追従し、読めなければ起動時に警告して `subagent` ツールなしで動く。定義 `~/.pi/agent/agents/*.md` は `agents-sync subagents` が `~/.claude/agents/*.md` から作る。`model` は `anthropic/<id>:<effort>` (Claude の effort low〜max は Pi の thinking にそのままある)。`model` の無い agent は呼び出し元のその時のモデルと thinking を引き継ぐので effort は写らない (Explore・Plan・general-purpose は Claude の low ではなく、今の段の thinking で動く)。`tools` は Pi の名前に直し (Glob は find)、対応の無いものは落とす。`disallowedTools` だけの agent は Pi の組み込みの道具から外した許可リストにして、読み取り専用を Pi でも守る。生成物は frontmatter の先頭に目印があり、元の md が無くなった目印つきのものだけを消す。子は `pi --mode json -p` で動き jev-gate も読み込むので、UI が無く、confirm の判定や分類器が使えないときの bash・write・edit は拒否になる。
- delegate: `extensions/delegate.ts` の `delegate` ツールで、Claude Code (`claude -p --output-format json`。モデル・effort・権限モードは Claude 側の設定のまま) か Codex (`codex exec -s workspace-write`) に 1 件任せて最後の答えを受け取る。claude.ai のコネクタ (Slack・Google・Claude Docs)・Chrome・独立レビューは claude、OS の隔離が要る作業は codex。子には herdr のペインの環境変数を渡さず (子の hook が Pi のペインの名前と状態を上書きしないように)、`CLAUDE_NOTIFY_PHONE=never` でスマホ通知を重ねない。Claude の費用は見積もり (サブスクリプションでは API 換算の目安) として返す。jev-gate の判定対象ではなく、任せた先の権限設定とサンドボックスが境界になる。

拡張 `dot_pi/agent/extensions/jev-gate.ts` は、path 引数を持つツールで `~/.ssh`・`~/.config/op`・auth.json・`*credentials*` などの保護パス (read と grep は `.env` も) をモデルを呼ばずに拒否し、bash は Claude Code の `~/.claude/hooks/injection-guard.sh` をそのまま呼んで同じ規則で止める (hook が無いと bash を拒否する)。
`notify.ts` は承認待ちと完了を `claude-notify` (`CLAUDE_NOTIFY_APP=Pi`) に渡し、Claude Code の Stop / Notification フックと同じ通知にする。

## 反映

反映は `run_onchange_after_agents-sync.sh.tmpl` が `agents-sync all` を呼ぶ。mcp.json・スキル名・subagent の md が変わったときだけ走る。
手で走らせるなら `agents-sync all [--dry-run]`。何度実行しても同じ結果で、消すのは中身が同一の複製と、元の md が無くなった Pi 用の subagent の生成物だけ (Codex 用は報告だけ)。`~/.pi/agent` が無いホストでは Pi の分を飛ばす。

## 追加のしかた (1 回書けば全部に入る)

- スキル: `dot_agents/skills/<name>/SKILL.md` を作って `chezmoi apply`。`npx skills add` で `~/.agents/skills` に入れたものも `agents-sync skills` が Claude 側にリンクする。
- MCP サーバー: `dot_agents/mcp.json` に名前・`command` / `args` または `type: http` と `url` を足して `chezmoi apply`。秘密の環境変数は `secrets` に名前だけ書く (値は書かない。自動では足されないので `claude mcp add -e` / `codex mcp add --env` / `pi mcp add --env` で 1 回入れる)。一部の道具だけに配るなら `"clients": ["pi"]` のように道具の名前 (`claude` / `codex` / `pi`) を並べる (例: Linear は Claude に claude.ai のコネクタがあるので Pi だけ)。後から `clients` で外しても、すでに入った道具からは消さない。
- subagent: `dot_claude/agents/<name>.md` を書く。Codex 用 toml と Pi 用 md は自動生成。
- 指示: `dot_agents/AGENTS.md` を直す。道具固有の規則は「道具ごとの差」に書く。

## 日本語の回答と ChatGPT / dot

個人の作業ポリシーと回答の書き方は `dot_agents/AGENTS.md` が正本。文字数の固定上限は設けず、自然な文と必要な説明を優先する。
ChatGPT の Settings > Personalization にある ChatGPT / Codex の custom instructions は、`agents-sync` の同期対象ではない。「作業と報告」の回答表現に関する項目を両方へ反映し、保存後に開き直して確認する。
dot の Custom rules に同じ文字数制限を重ねない。書き方は custom instructions、行動の許可は Custom rules に分ける。
この設定は生成時の指針であり、実際の読みやすさは新しい会話でも確認する。既存会話には古い指示やメモリが残ることがある。

## 個人設定と会社ルール

`dot_agents/AGENTS.md` は本人の既定。会社・顧客の状態管理、PR 承認、受入条件は各組織の正本に置く。
EFG の共通運用は [Linear の運用ルール](https://linear.app/efg/document/運用ルール-9b4270577ad2)、製品固有の指示は各 repo の `AGENTS.md`。この repo の `REVIEW.md` は chezmoi のレビュー時だけ読むリポジトリ用資料で、ホームへは配置しない。

## メモリの追記

Claude の `~/.claude/projects/<repo>/memory/` に1事実1ファイルで残す。Codex では `agent-memory-dir` で場所を確認する。
`<type>_<短い題>.md` に `name` / `description` / `metadata` (`node_type: memory`、`type: user|feedback|project|reference`) の frontmatter と、事実・理由を書く。
索引 `MEMORY.md` へ `- [題](ファイル名) — 一行の要約` を足し、200行・25KB以内に保つ。秘密・トークン・個人データは書かない。
Codex 自身の `~/.codex/memories` は自動生成物であり、手で編集しない。

## 公式の仕様 (確認した内容)

- Claude Code は `AGENTS.md` を標準で読む (v2.1.277 以降)。ただし `CLAUDE.md` がある repo では `CLAUDE.md` だけ。`@path` の読み込みは `~/.claude/CLAUDE.md` から `@~/...` も可 (ユーザー設定なので承認ダイアログなし)。ブロックの HTML コメントは読み込み時に除かれる。<https://code.claude.com/docs/en/memory>
- Claude Code のスキルは `~/.claude/skills/<name>/SKILL.md`。シンボリックリンクも読む。<https://code.claude.com/docs/en/skills>
- Claude Code の MCP はユーザースコープが `~/.claude.json`。`settings.json` に `mcpServers` を書く方法は文書にない。<https://code.claude.com/docs/en/mcp>
- Codex は各ディレクトリで `AGENTS.override.md` → `AGENTS.md` → `project_doc_fallback_filenames` の順に 1 つだけ読む。グローバルは `~/.codex/AGENTS.md`。上限 `project_doc_max_bytes` は既定 32KiB。<https://learn.chatgpt.com/docs/agent-configuration/agents-md>
- Codex のスキルは `~/.agents/skills` (ユーザー) と repo の `.agents/skills`。シンボリックリンクも辿る。`name` と `description` が必須。<https://learn.chatgpt.com/docs/build-skills>
- Codex の MCP は `config.toml` の `[mcp_servers.<name>]`。stdio は `command` / `args` / `env`、HTTP は `url`。OAuth は `codex mcp login <name>`。<https://learn.chatgpt.com/docs/extend/mcp>
- Codex の subagent は `~/.codex/agents/*.toml` (`name` / `description` / `developer_instructions` が必須)。`sandbox_mode` と `mcp_servers` は上書きできない。<https://learn.chatgpt.com/docs/agent-configuration/subagents>

## 共有できないもの

- 認証: MCP の OAuth は道具ごとに 1 回ずつ。Codex は `codex mcp login <name>`、Claude Code は `/mcp`、Pi は `pi mcp login <name>`。API キーなどの秘密は各道具の設定に残っている (dotfiles には置かない)。
- フック・権限・サンドボックス・モデル・effort: 形式も意味も違う。`~/.claude/hooks` と `~/.codex/hooks` は別々の複製。Codex のフックは内容のハッシュを本人が信頼登録する。
- スラッシュコマンド (`~/.claude/commands`): Claude Code だけ。Codex のデスクトップ取り込みはスキル (`source-command-*`) に変換するが、`agents-sync` は Claude に戻さない。
- subagent の `disallowedTools` (読み取り専用の強制): Codex に対応する設定がない。Codex 側は本文の指示だけが頼り。Pi は許可リスト (`tools`) に直して守る。
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
pi mcp list                               # Pi の MCP (つながるかも確かめる)
codex debug prompt-input hello            # Codex が読む指示・スキルの一覧 (モデル呼び出しなし)
agent-memory-dir                          # 今の repo の Claude メモリの場所
python3 tests/agents-sync.py              # 他に tests/agent-memory-dir.py, tests/codex-config.py
python3 tests/pi-settings.py              # 他に tests/pi-subagent.py, tests/pi-delegate.py (Pi が入っていれば本物の Pi でも確かめる)
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
