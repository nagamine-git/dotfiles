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

グローバル指示は `~/.pi/agent/AGENTS.md` で、`dot_pi/agent/AGENTS.md.tmpl` が共通の `dot_agents/AGENTS.md` に Pi 用の完了方針を足す。承認済みの通常作業は、実装・検証・対象を絞ったローカル反映まで進め、本人の TODO に回さない。
スキルは Pi が `~/.agents/skills` を標準で読むのでリンクは要らない。メモリは Codex と同じく `agent-memory-dir` で場所を知って読む。

- モデル: 既定 (default)・ここぞ (peak)・軽量 (light) の 3 段を `.chezmoidata/pi.yaml` に置き、`dot_pi/agent/modify_settings.json` (modify-template) が `~/.pi/agent/settings.json` の `defaultProvider` / `defaultModel` / `defaultThinkingLevel` (default 段)・`modelThinkingLevels` (3 段の `provider/id`)・`enabledModels` (Ctrl+P の順。`provider/id:thinking` で、切り替えると thinking も変わる) だけを上書きする。Pi が書くほかのキー (`lastChangelogVersion`・`deviceId` など) と `modelThinkingLevels` のほかの項目は残す。段の値はクラウドの model-radar が PR で直す。
- シェル: bash ツールと `!` コマンドは zsh で動く。`modify_settings.json` が `shellPath` (chezmoi の `lookPath "zsh"`。無ければ触らない) と `shellCommandPrefix` を書く。prefix は、pi-jev が起動のたびに対話の zsh から書き出したエイリアスと関数 (`~/.cache/pi/zsh-snapshot.zsh`、0600、`PI_ZSH_SNAPSHOT`) を読み、`setopt no_nomatch no_equals` で bash 流の `grep --include=*.ts` や `echo ===` を通し、`zsh -c` は後ろの行でエイリアスを展開しないのでコマンドを eval で読み直す (Claude Code と同じく source してから eval)。色やアイコンを付けるエイリアス (`ls` = eza) と、PATH のコマンドや組み込みと同じ名前のもの (`cc`・`ld`・`gm`・`vim` など) と `command_not_found_handler` は書き出さない。
  スナップショットは毎回 source されるので、pi-jev は書いたらファイルを 0400、ディレクトリを 0500 にし (作り直すときだけ書き込み権を戻す)、書いた中身の sha256 を `PI_ZSH_SNAPSHOT_SHA256` で渡す (入れ子の起動は親の値を引き継ぐ。作り直せなかったときは前のファイルを使わず、スナップショット無しで動く)。prefix は中身が一致するときだけ読む (違えば stderr に 1 行警告して、エイリアスと関数なしで続ける。確認は `command -p sha256sum` 1 回で約 1ms、prefix 全体で約 5ms)。確認と source の間の短い隙は残る (書き換えるには先に書き込み権を戻す必要があり、そのための chmod も下の規則で拒否される)。jev-gate は、そのディレクトリへの write・edit と、`~/.cache/pi`・`zsh-snapshot`・`PI_ZSH_SNAPSHOT`・`PI_JEV_WRAPPED` に触れる bash (読むだけでも) を拒否する。
  jev-gate は bash の判定の前に、コマンドの単語のうちエイリアスと関数を、スナップショットを読んだ `zsh -fc` 1 回 (約 5ms) で 3 段まで展開し、`# expanded:` として足してから決まった規則・injection-guard・分類器に渡す (`gpf!`・`ggf`・`ggfl` は force push として拒否)。展開できない (zsh が無い・時間切れ・読めない・3 段より深い・sha256 が違う) ときも素のコマンドを分類器にかけ、deny なら拒否、それ以外は confirm (UI が無ければ拒否。`JEV_GATE_MODE=allow` でも分類器が allow のときだけ通す)。実行時にコマンド名を組み立てる書き方 (コマンドの位置の `$(...)` や変数、組み立てた文字列の eval) は文字列から解決できないので、分類器の confirm の基準に入れてある。単純な静的コマンドでは、実際に呼ぶプログラムと引数・引用した heredoc の本文を区別する。実際の呼び出しがスナップショットのエイリアス・関数でなければ、本文中に名前があるだけでは展開しない。実際のエイリアス・関数、global/suffix エイリアス、動的な構文やシェルの再実行は従来どおり保守的に調べる。単語の分割・配列の添字・`${var,,}`・`mapfile` などは bash と違うまま。
- MCP: `agents-sync mcp` が `~/.pi/agent/mcp.json` を直接書く (Pi に add-json が無いため)。共有の定義から作るのは `command` / `args` / `url` だけで、`type`・`secrets`・`clients` は書かない。`enabled`・`exposure`・`toolExposure`・`description`・`oauth`・`env`・`headers` など本人や `/mcp` が足したキーと、`pi mcp add` で入れた Pi だけの定義は残す (後者は「Pi だけにある」と報告)。変更があるときだけ一時ファイルから置き換える。OAuth は `pi mcp login <name>` で 1 回ずつ (トークンは `~/.pi/agent/mcp-auth.json`)。
- subagent: `extensions/subagent.ts` が、動いている Pi の同梱例 `examples/extensions/subagent/index.ts` (`getExamplesPath()` の下) を読み込むだけの口で、写しは持たない。Pi を更新すると例も追従し、読めなければ起動時に警告して `subagent` ツールなしで動く。定義 `~/.pi/agent/agents/*.md` は `agents-sync subagents` が `~/.claude/agents/*.md` から作る。`model` は `anthropic/<id>:<effort>` (Claude の effort low〜max は Pi の thinking にそのままある)。`model` の無い agent は呼び出し元のその時のモデルと thinking を引き継ぐので effort は写らない (Explore・Plan・general-purpose は Claude の low ではなく、今の段の thinking で動く)。`tools` は Pi の名前に直し (Glob は find)、対応の無いものは落とす。`disallowedTools` は Pi の組み込みの道具 (`tools` があればその中) から外した許可リストにして、読み取り専用を Pi でも守る。Pi は範囲を表せないので、`Bash(git status*)` のような範囲つきの許可は落とし、範囲つきの禁止は道具ごと禁止する。道具が 1 つも残らない agent は、tools を書かないと Pi の既定の道具が全部渡るので Pi 用には作らない (前の生成物があれば消す)。生成物は frontmatter の先頭に目印があり、元の md が無くなった目印つきのものだけを消す。子は `pi --mode json -p` で動き jev-gate も読み込むので、UI が無く、confirm の判定や分類器が使えないときの bash・write・edit は拒否になる。
- delegate: `extensions/delegate.ts` の `delegate` ツールで、Claude Code (`claude -p --output-format json`。モデル・effort・権限モードは Claude 側の設定のまま) か Codex (`codex exec -s workspace-write`) に 1 件任せて最後の答えを受け取る。claude.ai のコネクタ (Slack・Google・Claude Docs)・Chrome・独立レビューは claude、OS の隔離が要る作業は codex。子には herdr のペインの環境変数を渡さず (子の hook が Pi のペインの名前と状態を上書きしないように)、`CLAUDE_NOTIFY_PHONE=never` でスマホ通知を重ねない。Claude の費用は見積もり (サブスクリプションでは API 換算の目安) として返す。子は作業場所の下ならどこでも書けるので、作業場所は Pi の作業ディレクトリかその下 (realpath で判定) に限り、`$HOME` そのものと、ホーム直下のドットディレクトリ (`~/.ssh`・`~/.config` など) の中は断る (Pi 自身がそのドットディレクトリの中で動いていれば、その下は許す)。子が返した文字列は、秘密鍵のブロックや `ghp_`・`sk-`・`ops_`・`xoxb-`・`AKIA` などのトークンらしい形を伏せ字にして、件数を添えて返す。jev-gate も bash と同じく判定し (ただし分類器が使えないときは素通しせず confirm)、作業場所が保護パス (資格情報・スナップショット) の中か、それを含むなら拒否し、作業場所と task の文にも決まった規則 (bash の規則に、資格情報の場所と `PI_JEV_*` を足したもの。task 自体には injection-guard を当てないが、自己テストの成功は委譲にも必要) を当ててから、`delegate harness=<h> cwd=<dir>` と task を分類器に渡す。task は地の文なので、`credentials` や `~/.ssh` のような語を含むだけでも拒否されることがある。作業場所は `~` を展開した realpath の 1 通りで解決し、`@` や `file:` で始まるものは断る。

拡張 `dot_pi/agent/extensions/jev-gate.ts` は、path 引数を持つツールで `~/.ssh`・`~/.config/op`・auth.json・MCP の OAuth トークン (`~/.pi/agent/mcp-auth.json`)・`*credentials*` などの保護パス (read と grep は `.env` も) をモデルを呼ばずに拒否し、bash は Claude Code の `~/.claude/hooks/injection-guard.sh` をそのまま呼んで同じ規則で止める (hook が無い、または Pi の起動後に試験コマンドを拒否しなかったときは、そのセッションの bash と delegate をすべて拒否して実行を止める)。hook は照合の前にコマンドの改行を空白に変えるので、行をまたいだ `curl … |` と `bash` も捕まる (無関係な行どうしで誤って拒否することもある。Claude Code 側にも効く)。
`notify.ts` は承認待ちと完了を `claude-notify` (`CLAUDE_NOTIFY_APP=Pi`) に渡し、Claude Code の Stop / Notification フックと同じ通知にする。

### Pi は通常作業の確認待ちを避け、保護を残す

jev-gate の既定は `auto`。分類器が `confirm` と判断しても確認画面で待たず、その操作だけを差し戻す。Pi は承認範囲内の読み取り専用・対象を絞った・可逆な代替手段で続ける。危険と判断された操作を別の道具やハーネスで実行してはならない。`/auto off` は従来の確認方式、`/auto on` は auto に戻す本人用のコマンドで、選択はセッションの有効な分岐に保存する。明示済みの環境設定がある場合はそちらを優先する。

- 分類の待ちは鍵の取得を含めて8秒で打ち切り、キャンセルも伝える。これは初期の運用上限で、実測した応答時間ではない。SDK がキャンセルに応じなくてもゲートは返る。実際のコマンドの実行時間や、別途走るフック・エイリアス確認の上限ではない。
- タイムアウトは許可にしない。「道具は未実行」と明示した一時障害だけは、同じ呼び出しを1回だけ再試行してよいと返す。危険判定やキャンセルではこの例外を使わない。自動のモデル切替や再送はしない。判定結果とタイムアウトには `duration_ms` を記録する。シェルの展開不能など別の不確かさもある場合は、その差し戻しを優先するが、分類器の障害は別に記録する。
- 認証ファイル・秘密・公開・破壊的操作の保護は維持する。Pi・Claude・Codex のゲート・フック・権限設定への直接編集と、それらを含む chezmoi apply は、分類器が allow としても本人の確認に回す。プロジェクト内の設定も対象にする。対象なし・強制・相対パスや展開など解釈できない引数の apply と update も同様。通常の apply は絶対パスか `~/` の対象を明記する。
- 制御ファイルの差し戻しは、普通の「安全な代替で続ける」と区別する。別の手段で同じ効果を実行せず、その対象は未反映として報告する。本人が確認方式を選んだ場合 (`/auto off` など) にだけ個別に承認でき、auto と従来の一括許可では通さない。delegate の task も制御ファイルの名前や chezmoi apply/update を含めば確認に回す。地の文なので読み取りの依頼でも誤って止める場合がある。対象を絞った通常設定の apply と dry-run は引き続き分類器で判定する。
- 短い公開ドキュメントの Context7 照会2種類だけは、分類器なしで通す。名前は完全一致させ、長い入力や秘密らしい文字列は除外する。ほかの MCP や「読み取り専用」という自己申告に自動で広げない。

ホーム全体を workspace 扱いにはしない。別のローカルプロジェクトは Git マーカーで範囲を確認するが、これは危険度の参考情報であり、本人の承認ではない。一般のスクリプトの効果は引き続き分類器が判断するため、このゲートは OS の sandbox の代わりではない。injection-guard の自己テストが失敗した場合は、auto でも実行を止め、delegate による回避も認めない。

### Pi は委譲前に利用枠を確認する

`extensions/usage-aware.ts` の `usage_status` は、Claude と Codex の利用枠の参考情報を読み取る。任意の `delegate`・`subagent` の追加や並列化の前に確認するよう、Pi に指示を渡す。`/usage` でも同じ情報と、その時点の autocompact 設定を表示できる。フッターの状態は取得時点のもので、アイドル中には更新しない。

- Claude は `claude-usage-cache --json` で既存のヘッダーキャッシュだけを読む。観測から5分経過、または保存されたリセット時刻を過ぎた値は `stale` とする。更新のために Haiku を呼ぶ `claude-usage --refresh` は実行しない。このキャッシュは Claude Code のプラン内残量や Fable 固有枠の証明ではない。
- Codex は既存の `model-route check --workflow review` だけを呼ぶ。版・認証・設定の検査を維持し、停止は `blocked`、取得不能は `unknown` にする。確認できた場合も、CLI アカウントの一般枠だけを表示する。通常の再確認は5分間キャッシュし、`/usage` は再取得する。モデルやスレッドは起動しない。
- 必要な機能・品質を先に決め、両方で要件を満たす任意の作業だけ、確認できた余裕を振り分けの参考にする。コネクタが要る Claude と OS sandbox が要る Codex は交換しない。不明・古い・欠けた窓を空き枠扱いせず、任意の並列化を抑える。

これはモデルを強制切替するルーターではない。Pi の直接呼出しと各 CLI のアカウント・課金経路が同じかは確認していないため、表示値を Pi 自体の残量として代用しない。モデル・effort・認証・権限は変えず、有料 API へのフォールバックも行わない。起動時の照会や定期ポーリングはなく、必要な確認だけを実行する。

autocompact は Pi の既定で有効。通常は残りコンテキストが16,384トークン未満になると古い会話を要約し、直近20,000トークンを残す。`/usage` はプロジェクト設定と現在のモデル別設定を含む実効値を表示するが、設定は書き換えない。要約自体にも推論が必要なので、利用枠の節約率は保証しない。

Fable を最上位に追加するときも、`pi update --models` と `pi --list-models fable` で実在する ID と thinking の対応を確認する。未確認の版を架空の ID で登録せず、別の版へ黙って置き換えない。

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
