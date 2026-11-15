# Claude Code・Codex・Pi の共通設定

どのリポジトリでも、リポジトリ側にファイルを足さずに Claude Code・Codex・Pi が同じ指示・スキル・MCP を使えるようにする。
正本はこの dotfiles (chezmoi)。`~` 側は直接編集せず、ここを直して `chezmoi apply` する。

## 共有しているもの

| 項目 | 正本 (このリポジトリ) | Claude Code | Codex |
|---|---|---|---|
| グローバル指示 | `home/dot_agents/AGENTS.md` → `~/.agents/AGENTS.md` | `~/.claude/CLAUDE.md` が `@~/.agents/AGENTS.md` を読み込む | `~/.codex/AGENTS.md` (`home/private_dot_codex/AGENTS.md.tmpl` が同じ内容を出す) |
| リポジトリの指示 | 各 repo の `AGENTS.md` / `CLAUDE.md` | v2.1.277 以降は `AGENTS.md` を標準で読む。`settings.json` の `pluginConfigs` で `CLAUDE.md` と両方読む | `config.toml` の `project_doc_fallback_filenames` に `CLAUDE.md` (`modify_private_config.toml` が保つ) |
| スキル | `home/dot_agents/skills/<name>/` → `~/.agents/skills/` | `~/.claude/skills/<name>` が上へのシンボリックリンク | `~/.agents/skills` を直接読む |
| MCP サーバー | `home/dot_agents/mcp.json` | `claude mcp add-json -s user` で `~/.claude.json` へ | `codex mcp add` で `config.toml` へ |
| subagent | `home/dot_claude/agents/*.md` | そのまま | `~/.codex/agents/*.toml` を生成 (モデルは指定せず effort だけ写す) |
| メモリ | Claude の自動メモリ `~/.claude/projects/<repo>/memory/` | 自動で読み書き | `agent-memory-dir` で場所を知り、指示どおり読み書き |
| 引き継ぎ | Linear のチケット / PR | 同左 | 同左 (セッションは共有されない) |

## Pi (am5-itx だけ。Claude Code と Codex をまとめて扱う主入口)

グローバル指示は `~/.pi/agent/AGENTS.md` で、`home/dot_pi/agent/AGENTS.md.tmpl` が共通の `home/dot_agents/AGENTS.md` に Pi 用の完了方針を足す。承認済みの通常作業は、実装・検証・対象を絞ったローカル反映まで進め、本人の TODO に回さない。
スキルは Pi が `~/.agents/skills` を標準で読むのでリンクは要らない。メモリは Codex と同じく `agent-memory-dir` で場所を知って読む。

- モデル: 既定 (default)・強め (strong)・ここぞ (peak)・軽量 (light) の 4 段を `home/.chezmoidata/pi.yaml` に置き、`home/dot_pi/agent/modify_settings.json` (modify-template) が `~/.pi/agent/settings.json` の `defaultProvider` / `defaultModel` / `defaultThinkingLevel` (default 段)・`modelThinkingLevels` (4 段の `provider/id`)・`enabledModels` (Ctrl+P の順。`provider/id:thinking` で、切り替えると thinking も変わる) だけを上書きする。Pi が書くほかのキー (`lastChangelogVersion`・`deviceId` など) と `modelThinkingLevels` のほかの項目は残す。段の値はクラウドの model-radar が PR で直す。
- 自動切り替え: `pi.yaml` の `router` が有効なら、既定の選択と Ctrl+P の先頭は仮想モデル `jev/auto` (`home/dot_pi/agent/extensions/jev-router.ts`、Pi 同梱の docs/virtual-models.md の仕組み) になる。本人の決定 (2026-11-15): Fable も自動で選んでよい。普段の知性の基準は Opus 5.5 medium。Claude と GPT は公平に扱う。総合点は 知性^6 × 安さ^2 × 速さ^1。近いものは黙って A/B テストし、成果で評価する。
  - 何が要るか: 本人のメッセージごとに Jev 分類器 (TypeSafe、鍵は op-agent で分類の時だけ読む) を 1 回呼ぶ。`level` は 5 段階の順序つきの点数 (light・standard・hard・deep・critical。0〜4 の期待値で、0.5 / 1.5 / 2.5 / 3.5 が境目)、`go` は「OK」「進めて」などの続行かどうか、`asked` はモデル名が文中にあるときだけ聞く (0.6 以上でそのモデルを使う依頼)。前の回答があれば、その成果を 3 つ聞く: `failed` (違う・動かない・やり直し)、`done` (結果を認めた・その上に進めた)、`shipped` (マージ・反映・公開・採用など実際に使った)。
  - 基準の点数: light は light 段の設定値の点数、standard は default 段の設定値の点数 (Opus 5.5 medium)、hard は +5、deep は default のモデルがどの effort でも届かない点数、critical は peak のモデルの最高点。
  - 選び方: 基準に届く Claude と GPT の全モデル・全 effort (Pi のモデル一覧にあり、サブスクで使えるもの) のうち、総合点 = (点数 × 本人の係数)^6 ÷ (コスト^2 × 時間) が最も高いもの。重みは `pi.yaml` の `router.weights`。2026-11-15 のデータでは、会話の最初は軽いが GPT-6.1 Terra medium、普通が GPT-6.1 Sol high、難しめが Fable low、深いが Fable high、最重要が Fable max。
  - 節約するモデル (`router.scarce`、本人 2026-11-15): Fable は週の枠の 50% までなので、総合点ではコストを 2 倍に数え、自動で選ぶ effort は high まで (max は「fable max」と名指ししたときだけ)。これで難しめは GPT-6.1 Sol max と Fable low の A/B になり、最重要も Fable high になる。Fable で続いた会話も、普通の依頼ではすぐ Sol に戻る。
  - モデルの切り替え: effort の変更はプロンプトキャッシュを保つが、モデルの変更は会話全体を書き直す (2026-11-15 の実測: モデル変更 6 回はキャッシュ読み取り 0、effort の変更 4 回は全量読み取り)。今のモデルを離れるのは、行きと帰りの書き直し費用 (文脈のトークン数 × 両方のキャッシュ書き込み単価) を足しても総合点が 2 倍以上のときだけ。文脈が相手のコンテキスト窓の 8 割を超えるモデルは候補にしない (Pi が圧縮してしまうため)。
  - サイレント A/B テスト: ある段階の上位 2 つの総合点が 3.3 倍以内 (係数 0.9〜1.1 がひっくり返せる幅 = (1.1/0.9)^6) で、どちらかの判定数が 30 未満なら、そのセッションのその段階に 2 つのどちらかを無作為に割り当て、セッション中は同じものを使う。本人には知らせない (フッターには実際のモデルが出る)。
  - 成果と本人の係数: 成果の 3 つの確率は、回答したモデル・effort・段階とともに `~/.pi/agent/jev-router.log.jsonl` に残す (本文は残さない)。`model-radar` が段階ごとに集計する。良い = max(done, shipped) + shipped (実際に使った結果は 2 倍)、悪い = 2 × failed。段階全体の良い割合 q0 に対して q = (良い + 20 × q0) ÷ (良い + 悪い + 20)、係数 = 1 + 0.5 × (q − q0) を 0.9〜1.1 に収めて点数に掛ける (順位にだけ使い、基準に届くかの判定には使わない)。
  - データ: `model-radar tick` (systemd のユーザー timer、毎時) が、Artificial Analysis の API (1 日 1 回) から Claude と GPT の各系統の最新モデルの effort ごとの点数・1 タスクのコスト・応答時間を取り、Pi での実測と本人の係数を合わせて `~/.pi/agent/model-scores.json` に書く。jev-router は次のメッセージで読み直す。報告は `~/.local/share/model-radar/index.html` (tailnet 内は https://am5-itx.tailcda87f.ts.net:8781/ )。
  - Pi での実測: AA の測定は AA の道具でのもの。ある段階で総合点が 10 倍以内に複数のモデルが並ぶ組み合わせ (と default・light 段) だけ、同じ小さな課題 3 件 (バグ修正・設定の調査・仕様からの実装、合否は機械判定) を `pi -p` で解かせ、時間・費用・合否を `~/.local/state/model-radar/bench.jsonl` に残す。3 組そろうと、実測の費用と時間を AA の尺度に直して (比の幾何平均が 1 になるよう割る) 総合点に使う。半分以上落とした組み合わせは候補から外す。毎時最大 12 件、組み合わせごとに 1 回 (30 日で測り直す)。Claude の枠が 80% を超えている間は Claude の分を待つ。測定用の Pi には jev-gate だけを読み込み、通知・MCP・AA の鍵は渡さない。
  - 続行 (`go` が 0.5 以上): 前の段階が standard 以上なら、今のモデルのまま、その段階 (critical のあとは deep) でいちばん総合点の高い effort。今のモデルがその段階に届かなければ選び直す。light のやり取りのあとの続行は、ふつうのメッセージとして振り分ける。
  - 名指し (fable/ここぞ・opus・sol/gpt・haiku/軽量で) の依頼はそのモデルを使い、名前の直後に書いた effort も使う。Fable の名指しは deep 以上。分類器が使えないときは名前だけで決める。
  - 利用枠のペース: Pi 自身の Anthropic サブスク応答のヘッダーから、アカウントの 5 時間枠・週枠と、モデル専用の枠 (Fable は `7d_oi`、Fable の応答にだけ付く) を記録する。枠の経過時間の割合より速く使っている枠は、その枠が持つモデルのコストを (使用率 ÷ 経過割合)^2 倍 (上限 4 倍) に数える。予定どおりかそれより遅ければ変えない。2026-11-15 22 時の例: Fable 枠 78%・経過 58% で Fable は 1.8 倍 (節約の 2 倍と合わせて 3.6 倍)、週枠 63% で Claude 全体は 1.2 倍。モデル専用の枠が 95% に達したら、そのモデルだけを外す。OpenAI の使用率は Pi の応答に出ないので、上限エラーのときだけ外す (Codex の表示では週 3%)。
  - サブスクが尽きたとき: Claude は Pi 自身の Anthropic サブスク応答のヘッダーで 5 時間枠・週枠のどちらかが 95% 以上、または明確なサブスク上限エラーで、そのプロバイダーを候補から外す (OpenAI は上限エラーだけ)。ヘッダーの欠落や観測の古さを回復とみなさない。高使用率だった全枠のリセット時刻か新しい低い値で戻る。上限エラーにはリセット時刻が無いので 1 時間後に試し直す。代わりはサブスクのモデルだけで、従量課金の API には切り替えない。何も残らなければ止める。Claude Code・Codex CLI の参考値は使わない。
  - 道具の結果の続きと再試行は同じモデルのまま。サブスクが尽きたときだけ移す (一般の 429・過負荷・認証・権限・安全上の停止・キャンセルでは移さない)。圧縮は default。分類器が使えない・6 秒で答えないときは今のモデルと effort か default。点数のデータが無ければ、段階の元の段 (light・default・peak) の設定値。セレクタの thinking は傾きで、low は hard まで、max は境目を 0.25 下げる。
  - 2026-11-15 の実測 (本人の過去のメッセージ、顧客の作業分は除く): 4 択 (light・standard・deep・continue) では 120 通のうち 30 通が peak の最高 effort になり、5 段階ではそのうち 5 通だけが残った。成果の判定は 110 通で確かめ、失敗は 9 通 (「ちがうよ！」「pi止まりすぎ」など)、成果ありは 19 通 (「mainマージしといて」「うまくいった」など) だった。テストは `tests/pi-router.py` (ルーターと model-radar) と `tests/pi-settings.py`。
- シェル: bash ツールと `!` コマンドは Pi 既定の bash で動く。zsh のエイリアスや関数は取り込まない。`pi-jev` は zsh を起動せず、古い `PI_ZSH_SNAPSHOT` と `PI_ZSH_SNAPSHOT_SHA256` も子へ渡さない。`modify_settings.json` は旧スナップショット用の prefix が残っている場合だけ `shellPath` と `shellCommandPrefix` を除く。本人が別に設定したシェルや prefix は残す。古いスナップショットのファイルは読み書きも削除もしない。
- MCP: `agents-sync mcp` が `~/.pi/agent/mcp.json` を直接書く (Pi に add-json が無いため)。共有の定義から作るのは `command` / `args` / `url` だけで、`type`・`secrets`・`clients` は書かない。`enabled`・`exposure`・`toolExposure`・`description`・`oauth`・`env`・`headers` など本人や `/mcp` が足したキーと、`pi mcp add` で入れた Pi だけの定義は残す (後者は「Pi だけにある」と報告)。変更があるときだけ一時ファイルから置き換える。OAuth は `pi mcp login <name>` で 1 回ずつ (トークンは `~/.pi/agent/mcp-auth.json`)。
- subagent: `extensions/subagent.ts` が、動いている Pi の同梱例 `examples/extensions/subagent/index.ts` (`getExamplesPath()` の下) を読み込むだけの口で、写しは持たない。Pi を更新すると例も追従し、読めなければ起動時に警告して `subagent` ツールなしで動く。定義 `~/.pi/agent/agents/*.md` は `agents-sync subagents` が `~/.claude/agents/*.md` から作る。`model` は `anthropic/<id>:<effort>` (Claude の effort low〜max は Pi の thinking にそのままある)。`model` の無い agent は呼び出し元のその時のモデルと thinking を引き継ぐので effort は写らない (Explore・Plan・general-purpose は Claude の low ではなく、今の段の thinking で動く)。`tools` は Pi の名前に直し (Glob は find)、対応の無いものは落とす。`disallowedTools` は Pi の組み込みの道具 (`tools` があればその中) から外した許可リストにして、読み取り専用を Pi でも守る。Pi は範囲を表せないので、`Bash(git status*)` のような範囲つきの許可は落とし、範囲つきの禁止は道具ごと禁止する。道具が 1 つも残らない agent は、tools を書かないと Pi の既定の道具が全部渡るので Pi 用には作らない (前の生成物があれば消す)。生成物は frontmatter の先頭に目印があり、元の md が無くなった目印つきのものだけを消す。子は `pi --mode json -p` で動き jev-gate も読み込む。auto は通常作業を固定ルールで通す。ask で確認が必要になった場合や制御ファイルの変更は、子に確認用の UI が無いため拒否する。
- delegate: `extensions/delegate.ts` の `delegate` ツールで、Claude Code (`claude -p --output-format json`。モデル・effort・権限モードは Claude 側の設定のまま) か Codex (`codex exec -s workspace-write`) に 1 件任せて最後の答えを受け取る。claude.ai のコネクタ (Slack・Google・Claude Docs)・Chrome・独立レビューは claude、OS の隔離が要る作業は codex。子には herdr のペインの環境変数を渡さず (子の hook が Pi のペインの名前と状態を上書きしないように)、`CLAUDE_NOTIFY_PHONE=never` でスマホ通知を重ねない。Claude の費用は見積もり (サブスクリプションでは API 換算の目安) として返す。子は作業場所の下ならどこでも書けるので、作業場所は Pi の作業ディレクトリかその下 (realpath で判定) に限り、`$HOME` そのものと、ホーム直下のドットディレクトリ (`~/.ssh`・`~/.config` など) の中は断る (Pi 自身がそのドットディレクトリの中で動いていれば、その下は許す)。子が返した文字列は、秘密鍵のブロックや `ghp_`・`sk-`・`ops_`・`xoxb-`・`AKIA` などのトークンらしい形を伏せ字にして、件数を添えて返す。jev-gate は、作業場所が資格情報の保護パスの中か、それを含むなら拒否する。作業場所と task の文にも固定ルールを当てる (bash の規則に、資格情報の場所と `PI_JEV_*` を足したもの)。task 自体には injection-guard を当てないが、自己テストの成功は委譲にも必要。制御ファイルに関係する task は本人確認に回し、それ以外は auto で通す。ask のときだけ `delegate harness=<h> cwd=<dir>` と task を分類器に渡す。task は地の文なので、`credentials` や `~/.ssh` のような語を含むだけでも拒否されることがある。作業場所は `~` を展開した realpath の 1 通りで解決し、`@` や `file:` で始まるものは断る。

拡張 `home/dot_pi/agent/extensions/jev-gate.ts` は、path 引数を持つツールで `~/.ssh`・`~/.config/op`・auth.json・MCP の OAuth トークン (`~/.pi/agent/mcp-auth.json`)・`*credentials*` などの保護パス (read と grep は `.env` も) をモデルを呼ばずに拒否し、bash は Claude Code の `~/.claude/hooks/injection-guard.sh` をそのまま呼んで同じ規則で止める (hook が無い、または Pi の起動後に試験コマンドを拒否しなかったときは、そのセッションの bash と delegate をすべて拒否して実行を止める)。hook は照合の前にコマンドの改行を空白に変えるので、行をまたいだ `curl … |` と `bash` も捕まる (無関係な行どうしで誤って拒否することもある。Claude Code 側にも効く)。
`notify.ts` は承認待ちと完了を `claude-notify` (`CLAUDE_NOTIFY_APP=Pi`) に渡し、Claude Code の Stop / Notification フックと同じ通知にする。

### Pi は通常作業を止めず、制御ファイルは本人が確認する

jev-gate の既定は `auto`。本人が依頼した通常作業は、固定ルールを通れば分類器も確認画面も使わず実行する。通常の push、検証スクリプト、`agents-sync all --dry-run`、対象を絞った通常設定の apply が、分類器の曖昧な確認で止まるのを避ける。MCP の呼び出しも auto では分類しない。ただし、auto は新しい範囲・本番変更・公開・課金・権限変更・破壊的操作の包括的な許可ではない。実行する agent が依頼と組織のルールを守る。

`/auto off` は分類器と確認画面を使う `ask`、`/auto on` は auto に戻す本人用のコマンド。選択はセッションの有効な分岐に保存し、別の分岐の選択は読まない。`JEV_GATE_MODE=auto|ask` があればそちらを優先する。それ以外の値 (`allow`・`deny` を含む) で対象の操作を許可することはない。

- **制御ファイルは本人確認を残す。** Pi・Claude・Codex のゲート・フック・権限設定への直接の write/edit と、それらを含む chezmoi apply は auto で拒否する。ソース、配置先、プロジェクト内の設定、シンボリックリンク経由も対象。ask でも分類器の allow だけでは通さず、本人が画面で確認した場合だけ許可する。UI が無い場合や確認を断った場合は拒否する。
- **反映対象を明示する。** 通常の apply は絶対パスか `~/` で対象を指定する。対象なし・強制・相対パスや展開など解釈できない引数の apply と update は本人確認に回す。apply の dry-run は、制御ファイルを含む対象でも変更しない検査として通す (update と強制指定を除く)。
- **別の経路で拒否を回避しない。** 制御ファイルの拒否は、普通の「安全な代替で続ける」と区別する。同じ効果を bash や別ハーネスで実行せず、独立した作業を進め、未反映の対象を報告する。delegate の task も制御ファイル名や chezmoi apply/update を含めば本人確認に回す。地の文なので読み取りの依頼でも止める場合がある。
- **固定の保護を両モードで使う。** 保護パス、ゲート用環境変数の変更・引き継ぎ、force push や package publish 等の固定拒否、injection-guard を維持する。Context7 の公開ドキュメント照会2種類は、秘密らしい入力を分類器やサービスへ送らず、監査ログにもその入力を残さない。injection-guard の自己テストが失敗したら、auto でも bash と delegate を止める。
- **分類器は ask だけで使う。** 鍵の取得を含めて8秒を上限とし、キャンセルも伝える。SDK がキャンセルに応じなくてもゲートは返る。タイムアウト・障害・長すぎる入力を許可へ変えず、本人確認に回す。UI が無ければ拒否し、自動再送や別モデルへの切替もしない。分類の記録には `duration_ms` を残す。8秒は実測の応答時間ではなく、ツールやフック自体の実行時間の上限でもない。

固定ルールは事故防止であり、OS の sandbox ではない。任意のプログラムによる同等の操作を完全には検出できない。auto では一般のスクリプトや MCP の危険度を分類器に委ねないため、本人の依頼の範囲を守ることが前提になる。

### 自律化は手順を増やさず、完了条件と実測で確かめる

[ISUCON2026 準備編](https://zenn.dev/luvtechno/articles/isucon2026-preparation)では、作り込んだ手順より薄い構成がよい結果を出した一方、評価環境の不備が判断を誤らせていた。競技での結果を普段の開発にそのまま一般化せず、共通指示には完了条件・変更前の状態・戻る先・行き詰まりの見直しだけを足す。固定フェーズ、大量の記録、毎ターンの監査役は追加しない。

検証の契約は次のとおり。通常作業の完了条件には、実装だけでなく必要な反映とその後の動作確認を含める。既存の正常な状態と本人の作業差分を保ち、計測やテストの不備と実装の不具合を区別する。モデル・effort・利用枠・承認境界は変えない。成功条件を満たしたら終え、失敗・上限・承認待ちに空の continue を送り続けない。

`python3 -B tests/agent-autonomy.py` は、共通指示が Codex と Pi に同じ本文で届くことと、CI の dry-run が失敗を隠さないことを検証する。仮の HOME と CLI を使い、モデル・秘密・ネットワークを使わない。dry-run の失敗は、後段の `tail` が成功しても CI の失敗として扱う。GitHub Actions の明示的な `shell: bash` は pipefail を有効にする ([公式仕様](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell))。

これは設定の伝達と決定論的な失敗検出の検証であり、長時間の自律実行の成功率や費用の改善を測ったものではない。記事の max 設定、安全停止後のモデル切替、自動再送は採用しない。既存の `/loop` の開始や設定変更も別の明示依頼として扱う。

反映前の残件: 共通指示3か所とゲートは本人確認の境界で未反映。ゲートの簡素化案には `JEV_GATE_*` の拒否ルールの欠落もあり、`tests/jev-gate.py` の `test_owner_gate_overrides_remain_denied_in_both_modes` が auto/ask の両方で失敗する。配置済みゲートにはこの保護が残っている。本人が確認方式を選び、ソースの保護復旧・回帰テスト成功・対象指定の diff/dry-run を確認するまでは反映しない。

### Pi からログイン済みの Chrome と PC の画面を使う

Claude Code の Claude in Chrome と Codex の Computer Use にあたるものを、Pi に 2 つ入れた (2026-11-15、本人の依頼)。

- **chrome** (`home/dot_agents/mcp.json`、Pi だけ、`agent-chrome-mcp`): Playwright MCP を `--extension --background` で、本人の Chrome に入れた Playwright Extension 経由でつなぐ。本人のログインのまま、ウィンドウを前に出さずに操作する。拡張機能の token (Agents vault の `playwright-extension`、参照は `~/.config/agents/chrome.env`) があれば接続の確認画面は出ない。token が無い間は、接続ごとに拡張機能が確認画面を出す。道具は `mcp__chrome__browser_*`。Google の chrome-devtools-mcp `--autoConnect` は、接続のたびに Chrome が許可を求め、なくせないのでやめた。
- **computer-use-linux** (`pi install npm:@agent-sh/computer-use-linux@0.7.53`、`~/.pi/agent/settings.json` の `packages`): 画面の読み取り・クリック・キー入力・ウィンドウ指定。`computer_use_linux_tools` で必要な道具を有効にすると、次のターンから `computer_use_linux_*` が使える。Hyprland では `hyprctl` でウィンドウを扱い、入力は `/dev/uinput` (本人は `input` グループ)。アクセシビリティのツリーには `gsettings set org.gnome.desktop.interface toolkit-accessibility true` が要る (設定済み。戻すなら `false`)。スクリーンショットは最初にポータルの許可が出る。npm の postinstall は走らず、実行ファイルは最初の呼び出しで同じリポジトリの GitHub Releases から取る (sha256 は同じ配布元のもので、改ざんの検証にはならない)。版は固定で、上げるときは中身を見直す。
- **live-gate** (`home/dot_pi/agent/extensions/live-gate.ts`): 対象 (chrome / desktop) ごとの動き方。既定は auto で、確認なしに見て操作する (UI の無い `pi -p` や subagent でも。本人 2026-11-15「毎回許可取らずに自律的に」)。`/live <chrome|desktop|all> <auto|ask|off>` で、セッションの分岐ごとに ask (最初の操作で 1 回確認) や off (操作を止める) に切り替えられる。見るだけの道具はどの設定でも通る。送信・購入・公開・削除・アカウント設定の変更は、本人がそれを頼んだときだけ行い、確認画面の手前で止めて報告するようシステムプロンプトに書く (誘導であって sandbox ではない)。PC の入力は Hyprland の background モードで、対象のウィンドウを前に出さずに送る。判断は `~/.pi/agent/jev-gate.log.jsonl` (layer `live`) に入力なしで残す。テストは `tests/pi-live-gate.py`。
- Claude Code の Claude in Chrome は、Pi の chrome で足りないときの予備として `delegate` (claude、`chrome: true`) で使える。PC が止まっていても動く定期実行は Claude Code のクラウドルーティンだけ。
- 旧 `zeed-browser` (chrome-devtools-mcp を 127.0.0.1:9222 へ) は、そのポートを使っていないので 3 つの道具すべてから外した。

裏で Pi を走らせるときは `--no-session` を付けず、`--session-dir` で記録を残す (成果の集計に入らなくなるため)。

### Pi を止めずに回す仕組み (2026-11-16)

- **auto-reload** (`extensions/auto-reload.ts`): 拡張機能 (`~/.pi/agent/extensions` の 1 段下まで)・`mcp.json`・`model-tiers.json`・`AGENTS.md` が、セッションを読み込んだあとに変わっていれば、対話画面で手が空いたとき (agent_settled) に `/reload` と同じ読み込み直しをする。`settings.json` は Pi 自身が書くので見ない。`pi -p` などの非対話の実行はそのまま終わる。古いセッションが古いルーターのまま利用枠の記録を上書きしていたため。テストは `tests/pi-auto-reload.py`。
- **/loop の一時的な失敗**: 利用上限・認証・課金・権限・安全上の停止・本人の Escape では今までどおり止める。それ以外 (ルーターや道具の不具合、通信・過負荷) は止めずに次の周期で続け、連続 3 回目で止める。テストは `tests/pi-loop.py`。
- **agent-claude** (`dot_local/bin`): Pi の delegate が起動する Claude Code。`~/.config/agents/claude-code.env` の参照 (Agents vault の `claude-code-oauth`、`claude setup-token` の長期トークン) が解決できれば `CLAUDE_CODE_OAUTH_TOKEN` を渡し、対話のログインの期限切れで落ちないようにする。無ければ素の `claude`。テストは `tests/agent-wrappers.py`。
- **Web 検索の予備**: 検索の道具が上限や障害のときは、ログイン済みの Chrome で検索する (Pi の AGENTS.md)。Radius の検索は従量課金なので本人の明示なしに使わない。
- **自動 push**: このリポジトリの main への commit は、`tests/*.py` が全部通ったら push する (リポジトリの AGENTS.md)。
- **tower を Pi で**: tower の実装エンジンを `--engine pi` で Pi (jev/auto) に替えられるようにする作業を、別ブランチ (`feat/pi-engine`) で進めている。

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

- スキル: `home/dot_agents/skills/<name>/SKILL.md` を作って `chezmoi apply`。`npx skills add` で `~/.agents/skills` に入れたものも `agents-sync skills` が Claude 側にリンクする。
- MCP サーバー: `home/dot_agents/mcp.json` に名前・`command` / `args` または `type: http` と `url` を足して `chezmoi apply`。秘密の環境変数は `secrets` に名前だけ書く (値は書かない。自動では足されないので `claude mcp add -e` / `codex mcp add --env` / `pi mcp add --env` で 1 回入れる)。一部の道具だけに配るなら `"clients": ["pi"]` のように道具の名前 (`claude` / `codex` / `pi`) を並べる (例: Linear は Claude に claude.ai のコネクタがあるので Pi だけ)。後から `clients` で外しても、すでに入った道具からは消さない。
- subagent: `home/dot_claude/agents/<name>.md` を書く。Codex 用 toml と Pi 用 md は自動生成。
- 指示: `home/dot_agents/AGENTS.md` を直す。道具固有の規則は「道具ごとの差」に書く。

## 日本語の回答と ChatGPT / dot

個人の作業ポリシーと回答の書き方は `home/dot_agents/AGENTS.md` が正本。文字数の固定上限は設けず、自然な文と必要な説明を優先する。
ChatGPT の Settings > Personalization にある ChatGPT / Codex の custom instructions は、`agents-sync` の同期対象ではない。「作業と報告」の回答表現に関する項目を両方へ反映し、保存後に開き直して確認する。
dot の Custom rules に同じ文字数制限を重ねない。書き方は custom instructions、行動の許可は Custom rules に分ける。
この設定は生成時の指針であり、実際の読みやすさは新しい会話でも確認する。既存会話には古い指示やメモリが残ることがある。

## 個人設定と会社ルール

`home/dot_agents/AGENTS.md` は本人の既定。会社・顧客の状態管理、PR 承認、受入条件は各組織の正本に置く。
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

`home/dot_local/bin/executable_slack-claude` (`~/.local/bin/slack-claude`)。Socket Mode で常駐し、本人 (user `U03L2HM8Q4X` かつ team `T03LKHSP0TW`) の発言だけを `claude -p` に渡して、結果をスレッドに返す。それ以外の人・bot・編集や削除などの subtype 付きは黙って無視する。

- 反応するもの: DM は全部。複数人 DM とチャンネルは、bot へのメンションか、bot が既に会話しているスレッド内の発言。受け付けたら元の発言に :eyes:、終われば :white_check_mark:、失敗は :x: とエラーの要約。
- スレッドごとに Claude のセッションを持つ (`~/.local/state/slack-claude/sessions.json`)。同じスレッドは到着順に 1 つずつ、別スレッドは並列。
- 権限・モデルは上書きしない (`agent-gateway` と同じく `~/.claude/settings.json` に従う)。`-p` では承認を答える人がいないので `--permission-prompts none` で、確認が要る操作は拒否になる。
- 作業ディレクトリは既定 `$HOME` (`SLACK_CLAUDE_CWD`)、タイムアウトは既定 30 分 (`SLACK_CLAUDE_TIMEOUT_SEC`)。claude には `SLACK_*` と `OP_SERVICE_ACCOUNT_TOKEN` を渡さない (secrets.env の他の値は渡る)。
- 鍵: 1Password の vault 'Agents' に `SLACK_APP_TOKEN` (`xapp-`、scope `connections:write`) と `SLACK_BOT_TOKEN` (`xoxb-`) を入れ、専用の `~/.config/agents/slack.env` に `op://Agents/...` の参照を足す。値は書かない。登録・確認手順は [agent-secrets.md](agent-secrets.md)。
- Slack app: Socket Mode を有効にし、Event Subscriptions に `app_mention` `message.channels` `message.groups` `message.im` `message.mpim`、Bot scope に `app_mentions:read` `channels:history` `groups:history` `im:history` `mpim:history` `chat:write` `reactions:write` `im:write`。
- サービス: `home/private_dot_config/systemd/user/slack-claude.service.tmpl`。am5-itx 以外では `home/.chezmoiignore` で外す。鍵を入れて `chezmoi apply` した後に 1 回だけ起動する。

```sh
systemctl --user enable --now slack-claude
op-agent run --env-file ~/.config/agents/slack.env -- slack-claude dm "通知テスト"     # 本人に DM が 1 通届く
python3 tests/slack-claude.py                                                          # ネットワークも claude も呼ばない
```
