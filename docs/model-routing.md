# am5-itx のモデル振り分け

通常の入口は `model-route`。既存 Codex の ChatGPT 認証と、ホーム設定の OpenAI モデル・effort を使う。
起動時にその値をコマンドスコープで固定し、project 設定によるモデル・providerの変更を防ぐ。
作業ディレクトリから親をたどる `.codex/config.toml` に接続先・provider・認証の上書きがあれば、通常入口は起動前に拒否する。
ホームのprofileに同種の上書きがある場合や、project設定がsymlink・不正形式の場合も停止する。設定値そのものは出力しない。
global のモデル・認証設定を変更せず、他端末には配置しない。
作業中の例外判断は共有スキル `model-routing` から行う。

## 現在の状態

OpenAI の通常入口と単発 `ask` の実行層を用意した。
Typesafe分類・Anthropic APIの**有料実行は停止中**で、課金POST送信・実費精算の実装は未完成。
予算証拠を入力すれば直ちに有効になる構成ではなく、確認後にその実行層と実経路テストを完成させる必要がある。
これはユーザー承認の不足ではなく、承認条件だったprovider側の予算上限確認が未完了のため。
残高の領収書・キー認証成功・ローカル予約額を、請求上限の証拠として扱わない。

2026-10-23 の読み取り結果:

| 操作 | 結果 | 確認できること |
| --- | --- | --- |
| Typesafe GET `/v1/models` | 200 | 指定キーによるモデル一覧アクセス |
| Anthropic GET `/v1/models` | 200 | Opus 5.5 / Fable 5.1 / Sonnet 5.5 が一覧にある |
| Anthropic GET `/v1/organizations/spend_limits` | 401 | このキー・要求で予算を読み取れなかった |

401 の原因が workspace scope・Admin API 資格・early access 利用資格のどれかは未確定。
呼んだのは Console 向け early access も記載された List APIで、Enterprise専用の `/effective` は呼んでいない。
`anthropic-version: 2026-10-21` と `anthropic-beta: spend-limit-reads-2026-09-26` を付けた。
TypeSafe公開OpenAPIにはモデル一覧GETと分類POSTだけがあり、残高・auto top-up・月額上限を読むAPIは特定できない。

## 入口と安全な単発相談

```sh
model-route                     # 普段の Codex
model-route doctor              # 認証と版のメタデータ。キー取得なし
model-route doctor --providers  # 用途別op-agentで正規GETだけを読み取る
model-route ask --task /tmp/task.json --context /tmp/reviewed-context.json
```

形式の例は `~/.config/model-routing/task.example.json` と `context.example.json`。
タスクごとに新しい UUID を作り、失敗やtimeoutの再送では同じ要求を新UUIDに付け替えない。
`ask` は承認待ち・拒否済みタスクを止める。通常はOpenAI、異なる修正仮説2回失敗か重要変更の独立レビューでOpus候補、明示した例外だけFable候補。
現在は有料API条件を満たせないので、Opus/Fable候補でも結果に `provider_budget_unverified` を記録してOpenAIへ戻す。
サブスク認証とAPI認証を相互に切り替えず、既存 `claude-delegate` の版検査は変更しない。

`ask` は空の一時ディレクトリ、read-only sandbox、ephemeral sessionで実行する。
コマンドスコープでshell・apps・MCP・plugin・browser・hooks・memoryを無効化し、私有repoは探索しない。
`hooks={}` では既存hookが併合されるため、検証した `features.hooks=false` を使う。
Codexの既存global指示は読み込まれ得る。`ask` を全global contextから隔離する機能とは扱わない。
新しい作業本文は明示してレビューした最小テキストだけを渡す。
結果は `configured_model` / `configured_effort` を表示する。native応答にモデルIDがなければ `reported_model: null` とし、実モデル名の自己申告を捏造しない。

## 明示 workflow と cc-implement (将来の新規起動だけ)

対象は、反映後に本人が明示して新しく起動する session だけである。
稼働中の thread・session・worktree、global の Codex / Claude 設定、`coder.md`、既存の `cc` は変更しない。
引数なしの `model-route` と `model-route start` は従来どおりホーム既定のモデル・effort を固定して起動し、quota の読取りに依存しない。
自動の復帰・格上げ・常駐 polling・収集は追加していないので、effort を変えるときは新しい明示起動で選び直す。

| 入口 | モデル / effort | 選ぶ理由 (事前情報) |
| --- | --- | --- |
| `model-route start --workflow review` | gpt-6.1-sol / xhigh | 通常のレビューで、既定と同じ Sol を明示的に固定する |
| `model-route start --workflow code-efficient` | gpt-6.1-terra / xhigh | AA の coding cost frontier の候補で、費用効率を試す |
| `model-route start --workflow routine` | gpt-6.1-terra / low | AA の coding cost frontier の候補で、定型作業に使う |
| `model-route start --workflow deep-review` | gpt-6.1-sol / max (条件付きで xhigh) | 重要なレビューで、一般枠の消費が大きいときだけ下げる |
| `cc-implement` | Claude Code coder / claude-opus-5-5 / xhigh | 実装は Claude を優先する本人の方針で、xhigh は本人の希望 |

deep-review は、一般 `codex` bucket が返した窓 (primary / secondary のうち null でないもの) のどれかが usedPercent 50 超なら xhigh に下げ、`downshift_reason` を記録する。
ちょうど 50 なら max のままにする。
`primary` を5時間枠とはみなさず、窓の長さは `windowDurationMins` だけで扱う (2026-10-30 の実測は primary が10080分の週枠で、secondary は null)。
usedPercent は使用済みの割合で、出力では `used_percent` とし、`remaining_percent` は 100 − usedPercent として別の名前で出す。
xhigh や low の workflow を max に上げる経路はない。

| 読取りの状態 | deep-review | 他の workflow |
| --- | --- | --- |
| app-server が起動しない、timeout、error 応答 | 停止する | quota を unknown と表示して続ける |
| 一般 `codex` bucket がない、または別 bucket しかない | 停止する | unknown として続ける |
| usedPercent が 0–100 の整数でない、または窓がすべて null | 停止する | unknown として続ける |
| `ordinaryUsageAllowed` が false | 停止する | 停止する |
| catalog に model / effort がない、実効設定が読めないか一致しない | 停止する | 停止する |

### 読取り確認 (check) と起動 (start)

`model-route check --workflow <名前>` は、既存の版・ChatGPT 認証・project 上書きの検査を通った後に、`base_command` と同じ接続先・認証の固定と workflow の model / effort 固定を付けた `codex ... app-server --listen stdio://` を一時的に起動する。
送るのは initialize (clientInfo) → initialized → `account/rateLimits/read` (`supportsLunaReserve: false`) → `model/list` (cursor でページ送りし、hidden は除く) → `config/read` (`includeLayers: false`) だけで、thread・turn・推論は開始しない。
読取り後は stdin を閉じて自分の子プロセス group だけを止め、共有 daemon の起動・停止・再起動はしない。
読取りは20秒・4 MiB で打ち切り、stderr は捨てる。accountId・workspace ID・raw config・origins・イベント・ログは出力しない。
deep-review で xhigh に下げたときは xhigh の固定で `config/read` をもう一度読み、最終の実効 model / effort が選択値と一致しなければ停止する。
出力 JSON には tool_version、configured / effective の model と effort、requested_effort、downshift_reason、quota の primary / secondary ごとの used_percent・remaining_percent・window_duration_mins・resets_at (unix 秒)、ordinary_usage_allowed、checked_at が入る。

`model-route start --workflow <名前>` は check と同じ確認を行い、stderr に `workflow_start` を1行出してから、選択した固定を付けた既存の native コマンドを通常の対話のまま起動する。
終了時には `workflow_finish` に exit_code・duration_seconds・quota_after を出し、token_usage・tests・rework は `unknown` とする。
quota_after は終了直後に1回だけ読んだアカウント全体の一般枠であり、このタスクだけの消費量ではない。

`cc-implement` は `claude --agent coder --model claude-opus-5-5 --effort xhigh --settings '<inline JSON>'` に通常の引数を続けて起動する。
inline JSON は profile と同じ `modelSettings` (`claude-opus-5-5` に `effortLevel: xhigh`) と、下の「subagent を含む固定」の4つだけを持つ `env` からなる固定の文字列で、キーを整列した同じ文字列を毎回渡す。任意の設定ファイル・環境変数・秘密を読み込んだり引数へ写したりはしない。
`~/.claude/profiles/coder-opus.json` は変更せず (稼働中の job が読んでいる可能性があるため)、従来どおり起動前に検査する。profile は `modelSettings` の `claude-opus-5-5` に `effortLevel: xhigh` を置くだけで、権限・認証・環境・hook のキーは持たない。内容が完全一致しない場合や symlink・欠落の場合は停止する。
`--model`・`--effort`・`--fallback-model`・`--agent`・`--agents`・`--settings`・`--setting-sources` (`=` 形を含む)、`-c` / `--continue`・`-r` / `--resume` (`-pc` のような結合形を含む)・`--fork-session`・`--from-pr`・`--teleport`・`--cloud`、API key 専用認証になる `--bare`、custom agent を無効にする `--safe-mode`、subcommand 名は、検証済みの新規 session の選択を無効にするので exit 2 で拒否する。
subcommand として扱うのは最初の operand だけで、各 option が native の定義どおりの数の値を消費した後で判定する。
値の数 (値なし・必須・省略可・可変長) と短縮形 (`-c` `-d` `-h` `-n` `-p` `-r` `-v` `-w`) は 2.1.314 の `claude --help` から写した表に従い、`-pn x` のような結合形も同じ規則で分ける。
必須の値は次の引数を無条件に取り (`--name -- update` の `--` は値)、省略可の値は `-` で始まる引数を取らない。可変長 (`--add-dir` など) は分けて書いたときだけ、次の option までの引数をすべて値として取る。
そのため `--debug mcp`・`--name update` の `mcp`・`update` は option の値として通し、`--name example update`・`--debug mcp auth`・`-p mcp`・`--verbose doctor` の最後の語は本物の subcommand として、認証確認や Claude の起動より前に拒否する。
表にない option、値を取らない flag への `=値`、表にない短縮文字は、後続の引数が値か subcommand かを判断できないので推測せず exit 2 で止める。native に option が増えたときは、表を更新するまで native claude を直接使う。
拒否の理由には option の名前・値や prompt を出さない。
`--dry-run`・`--observe` は wrapper 自身の option で、引数の先頭に並べたときだけ有効になる (`cc-implement --observe -p ...`)。
それより後に単独の引数として現れたものは、option の位置でも native option の値の位置 (`--name --observe`) でも exit 2 で拒否し、観測を勝手に有効にしたり引数から消したりしない。`--` の後の文字列と、`--append-system-prompt=--observe` のように `=` で結合した値は native の引数としてそのまま渡す。
`CLAUDE_CODE_EFFORT_LEVEL` は `--effort` より優先されるため、呼出し元の値が空でなく xhigh 以外なら競合として止め、黙って上書きも unset もしない。子へ渡す xhigh は、検査を通った後に下の固定として付ける。
`ANTHROPIC_API_KEY`・`ANTHROPIC_AUTH_TOKEN`・`ANTHROPIC_BASE_URL`・`CLAUDE_CODE_OAUTH_TOKEN`・`CLAUDE_CONFIG_DIR`・`CLAUDE_CODE_USE_*` がある場合と、`claude auth status --json` が既存の firstParty claude.ai Pro/Max を示さない場合は、変数名だけを示して exit 78 で止め、認証経路は切り替えない。
認証確認が通った後に `claude --version` を1回だけ読み、`X.Y.Z (Claude Code)` と解釈できて 2.1.292 以上のときだけ起動する。unknown・解釈できない出力・読取りの失敗・古い版は exit 78 で止め、install・upgrade・版検査の省略はしない。読んだ値はそのまま start 行の `version` に使う。
起動前に stderr へ `cc_implement_start` (model・effort・`subagent_model`・`subagent_effort`・`subagent_scope: all`・`min_cli_version`・version・started_at)、終了後に `cc_implement_finish` (exit_code・outcome・duration_seconds、usage・tests・rework は `unknown`、`implementation_verified: false`・`fallback_allowed: false`) を出し、prompt や引数は記録しない。launcher による retry・idle timeout・fallback はない。
`--observe` なしの起動は従来どおり native の端末表示と exit code だけで、TUI 自身の UI があるため下の phase は出せない。
`cc-implement --dry-run` は固定の tool・agent・model・effort・subagent の固定と範囲・必要な最低版・profile のパス・選択フラグ (inline JSON を含む) だけを表示し、Claude を起動せず、CLI を探すことも版を読むこともしない。

#### 無人実行の観測 (`--observe`)

親の agent や script から無人で実装を呼ぶときは、必ず `cc-implement --observe --print ...` を使う。
`--observe` は `--print` (`-p`) と一緒のときだけ受け付け、native に `--output-format stream-json --verbose` を付ける。別の `--output-format` が指定されていれば黙って上書きせず、値を表示せずに exit 2 で止める。
stdout には native の stream-json をそのまま流す。stderr には wrapper の記録 (`record` が `cc_implement_start` / `cc_implement_phase` / `cc_implement_finish` の JSON 行) を出す。native 自身の stderr も同じ stderr に出るので、`record` キーで区別する。

| phase | 出す時点 | 主な項目 |
| --- | --- | --- |
| `auth_check` | `claude auth status --json` を読む直前 (`state: checking`)、読めなかったとき (`unverified`)、読めたが条件に合わないとき (`not_subscription`) | 読取りは `metadata_timeout_seconds: 15` で打ち切る。失敗・timeout・解釈できない応答は認証失敗と判定せず `unverified` とし、どちらも exit 78 で止める |
| `launch` (`cc_implement_start`) | 認証確認が通り、起動する直前 | `auth_check: passed`、`idle_timeout: null`、`launcher_retries: 0` |
| `waiting` | 子プロセスを起動した直後 | native の init を待っているだけで、失敗の意味はない |
| `initialized` | `type=system`・`subtype=init` | `configured_model`、`actual_model`、`model_match`、`cli_version` |
| `running` | 最初の assistant か tool_result | `first_event` |
| `api_error` / `api_retry_observed` | assistant の `error`、`system`・`api_retry` | 既知コードだけの `error_code`・`error_class`、`http_status` |
| `model_mismatch` | main または入れ子の agent で固定と違う model が報告された | `source` (`init` / `assistant` / `subagent`)・`actual_model` (main)・`mismatched_model`。自分が起動した子にだけ SIGTERM を1回送る |
| `terminal` (`cc_implement_finish`) | native の終了後 | `outcome`・`reason`・`exit_code`・`native_exit_code`・`mismatch_source`・`subagent_models`・`configured_effort`・`actual_effort: unknown`・token 数 |

出力のない時間がどれだけ続いても、timeout・接続失敗・モデル利用不可とは扱わない。
idle や推論の timer、launcher の retry、別の model・tool・実装者への自動切替はなく、子プロセスが動いている間は終了させずに読み続ける。
エラーの分類は、native が出した既知のコード (`authentication_failed`・`billing_error`・`rate_limit`・`overloaded`・`server_error`・`invalid_request` など) か、明示された HTTP status (401/403・429・5xx) だけから行う。
接続 (`connection`) に分類するのは `connection_error`・`connection_timeout` という明示コードが来たときだけである。2.1.314 の stream の error 定義には接続専用のコードがなく、status なしの `unknown` は `unclassified` のままにする。
無音・EOF・解釈できない行から接続エラーや「Claude が使えない」とは推測しない。解釈できない行は数を数えるだけにする。
native の `api_retry` は観測した retry として記録するだけで、launcher は retry を足さない。
エラー文・本文・prompt・tool の入出力・session ID・cwd は記録しない。stream と記録はどちらもファイルに保存せず、常駐の収集や polling もない。
session の保存は native の既定のままで、wrapper は `--no-session-persistence` を付けない。

outcome と exit code は上の行から順に判定する。

| outcome (`reason`) | 条件 | exit code |
| --- | --- | --- |
| `error` (`model_mismatch`) | init、最上位の assistant、または入れ子の assistant (subagent など) の model が固定と違う | 4 |
| `interrupted` (`native_interrupted`) | signal による終了 (SIGINT 130・SIGHUP 129・SIGTERM 143 など)、または native の 130 / 143 | native の値 (SIGINT は 130) |
| `error` (`native_exit_nonzero`) | native の exit code が 0 以外 | native の値 |
| `incomplete` (`missing_init` / `missing_result` / `malformed_result`) | exit 0 なのに init や terminal result がない、または result の形式が不正 | 3 |
| `error` (`result_error`) | result が `is_error: true`、または `subtype` が success でない | 1 |
| `completed` (`cli_completed`) | 上のどれにも当たらない | 0 |

`completed` は CLI が完了したという意味だけで、編集やテストの成否は証明しない。finish 行は常に `implementation_verified: false`・`tests: unknown`・`rework: unknown`・`fallback_allowed: false` で、実装の確認は親が差分とテストで行う。
model は `claude-opus-5-5` と完全一致するか、同じ ID に日付 `-YYYYMMDD` が付いたものだけを一致とする。この規則は main と、入れ子の agent の通常の assistant message (`parent_tool_use_id` または `agent_id` があるもの) の両方に同じように使う。native の `<synthetic>` message と model のない message は判定の対象外。
入れ子の message で不一致になっても `actual_model` は main の model のままにし、違った model は `mismatched_model` と `source: subagent` で別に示す。`subagent_models` は入れ子の message を整形済みの model 名ごとに数えたもので、tool_use ID・agent ID・prompt・本文は記録しない。
`model_usage` の model 名は判定に使わない。native の内部の分類器などは agent とは限らないため、そこに別の model が出ても不一致にしない。
effort は stream・環境変数・`model_usage` のどれからも推定せず、finish 行は `configured_effort: xhigh` と `actual_effort: unknown` を分けて出す。
token 数 (`usage` と model ごとの `model_usage`) は数値だけを出す。`total_cost_usd`・`costUSD` は API 換算の定価でありサブスクの消費ではないので出さない。
`--observe` の子は print 専用なので、別の session・process group (`start_new_session=True`) で起動する。端末の Ctrl-C は wrapper にだけ届き、子へ二重に届かない。
wrapper は受けた SIGINT / SIGTERM / SIGHUP を、受けた回数だけ1回ずつ自分が起動した子にだけ中継し、子の起動中に届いたものは起動直後に送る。SIGHUP を含めるのは、別 session の子には端末の切断が届かないためである。
Ctrl-Z・Ctrl-\ は中継しないので、停止・終了するのは wrapper だけで子は動き続ける。止めるときは Ctrl-C か SIGTERM を使う。他のプロセスには signal を送らない。
`--observe` なしの対話 TUI は従来どおり端末と同じ process group で動き、Ctrl-C は TUI 自身が処理する。

#### subagent を含む固定 (この wrapper の新しい起動だけ)

`--model` は main session だけを固定するので、以前は main が Opus 5.5 / xhigh でも、coder が起動した入れ子の coder が frontmatter や Agent 呼出しごとの model 指定で Sonnet になり、そのまま編集できた。
native の subagent の model は、呼出しごとの指定 > frontmatter > `CLAUDE_CODE_SUBAGENT_MODEL` > main の順に決まる。そこで wrapper は次の4つの値だけを子に渡す。

| 変数 | 値 | 働き |
| --- | --- | --- |
| `CLAUDE_CODE_SUBAGENT_MODEL` | `claude-opus-5-5` | subagent の既定 model |
| `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` | `1` | 上の値を frontmatter と呼出しごとの指定より優先し、Agent の起動 parameter から model を除く (2.1.257 以上) |
| `CLAUDE_CODE_EFFORT_LEVEL` | `xhigh` | frontmatter と呼出しごとの effort より優先する (呼出しごとの effort は 2.1.292 以上) |
| `CC_IMPLEMENT_USAGE_NO_MODEL_CALL` | `1` | model を選ばない。今はどこからも読まれない (下の「usage telemetry の refresh」) |

同じ4つを inline `--settings` の `env` と、子プロセス用に `os.environ.copy()` した環境の両方に入れる。shell の環境だけでは、優先度の低い settings ファイルの `env` (user 設定の既定 `CLAUDE_CODE_SUBAGENT_MODEL=opus` など) に上書きされ得るため、user・project・local の settings より上位の CLI 引数の settings に置く。
既存の user 設定の既定 `opus` は、この明示経路の中だけで `claude-opus-5-5` に置き換わる。global の振り分け、`cc`、`model-route`、settings ファイル、呼出し元の `os.environ` は変えず、子の環境では4つ以外の変数・端末・stdin / stdout・cwd・signal の扱いを従来どおりに保つ。
managed policy は CLI 引数よりさらに上位なので、そこで model が差し替えられた場合は成功ではなく `--observe` の不一致として扱う。
4つの値は呼出し元が同じ名前を設定していても子の側で上書きし、競合とはしない。ただし `CLAUDE_CODE_EFFORT_LEVEL` が xhigh 以外なら、従来どおり起動前に exit 2 で止める。

範囲は、この起動の main・subagent・teammate・workflow agent のすべてである。Explore やレビュー用の agent も Opus 5.5 / xhigh になり、fork / inherit は同じ固定の main を引き継ぐ。
子孫のプロセスは4つの値を環境として受け継ぐ。そのため、この session の Bash tool や hook から別の native `claude` を起動すると、その中の subagent も Opus 5.5 / xhigh に固定される。
費用の境界として、Explore などの安い既定 model よりサブスクの枠を多く使う可能性がある。これは本人が実装の品質を優先して承認した選択で、費用の Pareto や利用枠の削減を主張するものではない。増加量は測定していない。
通常の `cc`・`model-route` の workflow・既存の Pareto 候補は変えないので、安い既定で調べたいときは cc-implement の外で行う。

設定値と実際の値は区別する。dry-run と start 行の `subagent_*` は設定値で、native が実際にその model・effort で動いた証明ではない。
`--observe` は stream に出た main と入れ子の model を照合し、違えば exit 4 で止める。effort は stream から読まないので、常に `actual_effort: unknown` である。実際の model / effort は、native の `/tasks` の表示や session の header で別に確かめる。
FORCE は native が subagent を選ぶ前の強制である。`--observe` の不一致は起きた後の検出であり、止めるまでにその agent が編集を済ませていないことは保証しない。`--observe` なしの起動では、FORCE だけが強制になる。

新たな保護の迂回はない。認証・provider・権限・tool・MCP・sandbox・trust・安全用 hook の設定は変えず、effort 競合・認証 override・option 解析・`--settings` などの拒否も従来どおりである。4つの名前は認証・provider の検査対象 (`ANTHROPIC_*`・`CLAUDE_CONFIG_DIR`・`CLAUDE_CODE_USE_*`) と重ならない。

##### usage telemetry の refresh

global の Stop hook は usage を refresh しない。`claude-usage --refresh` は固定の Haiku に送信してモデルを起動し、Stop のたびに利用枠を使うためである (docs/agent-lifecycle.md、tests/claude-usage-cache.py)。
以前は am5-itx の Stop hook に、`CC_IMPLEMENT_USAGE_NO_MODEL_CALL` が `1` のときだけ飛ばす条件付きの refresh があったが、外した。wrapper はこの変数を今も子に付けるが、読む hook は無い。
そのため、cc-implement の起動でも通常の起動でも、Stop では quota の snapshot が更新されない。その値は古いか unknown として扱い、新しい値があるかのように記録しない。
global の source と runtime の間には、この変更とは無関係の model / effort の既存のずれがあり、bootstrap はそれを保持した。ここでは直していない。そのずれは source から settings をそのまま再反映すると変わり得るので、別に判断する。

#### 強制できる範囲

wrapper が起動するのは native の `claude` だけで、Codex や別の実装経路は呼ばない。
入れ子の agent の model は上の FORCE で起動前に固定し、`--observe` ではさらに不一致を検出して止める。
不完全・エラー・中断の実行は、0 以外の exit code と `fallback_allowed: false` によって fail closed で報告する。
ただし、親のプロセスが wrapper の外でファイルを編集することは技術的には止められない。`fallback_allowed: false` や prompt・指示書の記述は記録と取り決めであり、全体への強制ではない。

反映後の確認は次のコマンドで行う。

```sh
model-route check --workflow review
model-route check --workflow code-efficient   # 実 catalog に gpt-6.1-terra / xhigh があるか
model-route check --workflow routine          # gpt-6.1-terra / low
model-route check --workflow deep-review      # 一般枠の窓と max / xhigh の判定
cc-implement --dry-run                        # 固定の選択・subagent の固定・profile のパスだけ。推論なし
cc-implement --dry-run --observe -p           # 無人実行で付ける stream-json の固定も表示。推論なし
cc-implement                                  # 対話 header が "Opus 5.5 with xhigh effort" か、/tasks の subagent の model・effort を目視する
```

### 変更前後と根拠の限界

| 項目 | 変更前 | 変更後 | 理由 |
| --- | --- | --- | --- |
| `model-route` の版検査 | `codex-cli 0.163.0` 完全一致 (0.166.0 では停止) | `codex-cli 0.166.0` 完全一致 | 実機 0.166.0 の CLI と app-server を確認したため。wildcard は許可しない |
| Codex のモデル選択 | ホーム既定の1種類 | 既定は不変で、明示 workflow だけ4種類 | 作業の種類ごとに費用と深さを選ぶため |
| Claude の実装入口 | coder frontmatter は sonnet / xhigh、`cc` は sonnet 固定 | `cc` はそのままで、`cc-implement` だけ Opus 5.5 / xhigh | 稼働中のタスクに影響させず、未来の起動だけを変えるため |
| `cc-implement` の subagent | main だけ固定し、入れ子の coder は Sonnet になり得た (`--observe` も対象外) | この起動の全 agent を Opus 5.5 / xhigh に FORCE で固定し、`--observe` は入れ子の不一致も exit 4、CLI は 2.1.292 以上 | 入れ子の Sonnet の coder が実際に編集したため。費用より実装の品質を優先する本人の承認による |

check の成功は catalog と実効設定に選択値が載っていることの確認であり、推論の成功や、実際に応答したモデル・effort の証明ではない。実際の応答は session の header や最初の turn で別に確かめる。
AA (Artificial Analysis) の Coding Agent の API 費用 Pareto は試すための事前情報であり、本人のサブスク消費の予測や約束ではない。
Terra の low / xhigh は AA の coding cost frontier の候補であり、本人の作業での品質は未検証である。
Opus 5.5 の xhigh は本人の希望による選択であり、AA の Opus 5.5 Max の benchmark は xhigh の性能を証明しない。
Gemini Carbon、新しい支出・サービス・polling は追加しない。
既存 `claude-delegate` の text-only の版検査 (2.1.301) は変更していない。実機 2.1.314 では未検証のため版検査で停止するが、迂回や削除はしない。

### 最小の記録とロールバック

開始時は stderr の start 行 (入口・model・effort・requested_effort・downshift_reason・開始時 quota・版・時刻) を、終了時は finish 行 (exit_code・所要時間・quota_after) をタスク報告に残す。
tests と rework は wrapper が `unknown` と出すだけなので、実測は担当者がタスク報告に書く。
quota の50超・unknown・停止・反復失敗で別の workflow に選び直すときは、理由と新しい start 行を記録し、実行中の thread の設定は変えない。

反映前のファイルは親作業がバックアップディレクトリに保持している。
`model-route` を戻すときはバックアップの source に戻し、対象を指定した chezmoi diff / apply を行う。旧版検査 0.163.0 に戻すと、実機 0.166.0 では起動前に停止する (fail closed)。
`cc-implement` と `~/.claude/profiles/coder-opus.json` は新規ファイルなので、source と反映済みの2ファイルを削除すれば戻る。global 設定は変えていないので戻す必要はない。
subagent の固定は wrapper の引数と子の環境だけにあるので、wrapper を以前の版に戻せば消える。usage を refresh する Stop hook は無いので、wrapper を戻しても usage の扱いは変わらない。

## 秘密・個人情報と状態

EFGの非公開仕様・差分を渡す場合は、秘密・個人情報を人がレビューして除いた最小部分だけを `efg_private_sanitized` として用意する。
メール・電話・個人ホームのパスの自動マスクは補助であり、氏名や内部個人IDまで完全に判定するものではない。
既知の鍵形式、Authorization、秘密らしい代入、秘密参照、秘密鍵ブロックを検出したら送信前に拒否する。
個人の非公開資料、認証ファイル、セッション原文、repo全体の自動収集は入力にしない。
Typesafeへ送ってよいのは固定の匿名メタデータだけで、原文・コード・UUIDは対象外。

状態は `~/.local/state/model-routing` に本人だけが読める権限で保存する。
保存するのはUUID・ハッシュ・状態・提案・模擬予約だけで、作業本文やモデル応答は保存しない。
呼出し前に排他予約し、同一UUIDの二重呼出しや内容変更を拒否する。
timeout・プロセス異常・不明な結果では `uncertain` を残し、再送しない。
APIが将来有効になる場合には、providerの結果・課金の照会を含む精算処理を追加する必要がある。

## 予算と実接続前に必要な確認

ローカル設定の最大値はAPI合計月額2,000 cents、1件目安500 cents。
これらは入力ガードであり、providerの請求を保証する仕組みではない。
現状ではAPIのPOSTを送らないことによって、未確認の追加課金を防いでいる。
各providerに$20ずつでは合計条件を超える。両方を使うには、強制上限の合計が$20以内となる分割を確認する。
新規Admin key、権限追加、auto-refill有効化、購入、契約変更、他端末への展開は行わない。

本人に必要なのは広いAdmin keyの共有ではなく、既存画面の読み取り確認:

1. [Anthropic Workspaces](https://platform.claude.com/settings/workspaces) で使用中キーのworkspaceを開き、Spend limitsの月額上限・当月消費・キーとの対応を確認する。
2. [Anthropic Billing](https://platform.claude.com/settings/billing) で残高、prepaidか請求書払いか、auto-reloadがOFFかを確認する。設定の変更や購入はしない。
3. [Typesafe Billing](https://console.typesafe.ai/settings/billing) で指定キーのorganizationを選び、Available credits・auto top-up・月額の強制上限の有無を確認する。領収書だけでは代用できない。

この実行環境には既存ログインブラウザを読むツールが露出しておらず、標準の既存CDP接続口も見つからなかった。
公開WebからTypeSafe Billingへアクセスするとログイン画面になるため、ログイン・権限変更を勝手に行わない。
画面で予算条件が確認できても、その時点では有料実行層を別途完成・レビューし、無害な入力で確認する。
EFG-181は、それらの実経路が未確認の間は完了にしない。

## 検証

```sh
python3 -B tests/model-route-plan.py
python3 -B tests/model-route.py
python3 -B tests/cc-implement.py
```

テストは合成入力と偽プロセスのみで、実キー・モデル・ネットワークを使わない。
app-server の通信テストは、合成の偽 stdio サーバーを子プロセスとして使い、実際の Codex は起動しない。
配布は `.chezmoiignore` の既存ホスト条件に従いam5-itxだけ。反映は必ず対象を指定したchezmoi diff / dry-run後に行う。
