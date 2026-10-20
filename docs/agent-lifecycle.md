# Claude / Codex の接続受付と作業のライフサイクル

方針・役割・終了・認証の正本は [lab の runbook](https://github.com/efg-technologies/lab/blob/main/ops/runbooks/agents.md)。この repo はホスト設定の実装を持つ。

## 設定

- `dot_local/bin/executable_agent-gateway`: native RC を worktree / capacity 1 / 会話の事前作成なしで起動。モデル・effort・権限を上書きしない。
- `private_dot_config/systemd/user/claude-ops-gateway.service.tmpl`: Linux の user service。
- `Library/LaunchAgents/com.efg.claude-ops-gateway.plist.tmpl`: macOS の LaunchAgent。
- `dot_local/bin/executable_claude-statusline`: native `session_name`。表示のためのモデル呼び出し・会話本文読み取り・要約キャッシュを持たない。
- `dot_tmux.conf.tmpl`: `@agent-role` のある pane は役割を、無い pane は通常の title を表示する。

## 初回配置

対象ファイルだけを `chezmoi diff` / `apply --dry-run --exclude scripts` で確認する。
受付の anchor は編集用 chezmoi source と分ける。次は OS サービスをロードする前に 1 回だけ実行する。

```sh
mkdir -p ~/.local/share/agent-workspaces
git -C ~/.local/share/chezmoi worktree add --detach ~/.local/share/agent-workspaces/dotfiles HEAD
```

Linux は `systemd-analyze --user verify` → `systemctl --user enable --now claude-ops-gateway.service`。
Mac は `plutil -lint` → `launchctl enable "gui/$(id -u)/com.efg.claude-ops-gateway"` → `launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.efg.claude-ops-gateway.plist`。
認証は各機の通常のターミナルで保存する。認証を source repo にコピーしない。

認証待ちでは Linux を `systemctl --user disable --now claude-ops-gateway.service`、Mac を `launchctl disable "gui/$(id -u)/com.efg.claude-ops-gateway"` と bootout で停止する。認証を保存してから上の手順で有効化する。

既存受付の移行時は native の busy / idle、子の処理、予定、入力を確認し、完了して待機しているものから終了する。会話・worktree・未コミット変更を消さない。Desktop、ブラウザ連携、Codex の補助処理を担当者の重複として止めない。

## 検証

```sh
bash -n dot_local/bin/executable_agent-gateway dot_local/bin/executable_claude-statusline
python3 tests/agent-lifecycle.py
shellcheck dot_local/bin/executable_agent-gateway dot_local/bin/executable_claude-statusline
```

テストは使い捨て HOME と fake CLI で native 引数を確認し、表示がモデルを呼ばないことを検証する。認証・実際の登録・再起動・スマホの確認は runbook に記録する。

## Sol から Claude Code への限定課題の引き渡し

通常は既定の Sol 6.1 を使う。同じ失敗を繰り返す、仮説を変えても進展しない等のときは、失敗の内容と試した変更を報告し、Claude に渡す一問を準備する。ベンチマーク順位だけでタスクを丸ごと転送しない。定期実行・無制限再試行はしない。

`~/.local/bin/claude-delegate` は、既存の Claude CLI の `--print --output-format json` を使う一回限りの受け渡し役。既存 `agent-gateway` はブラウザ・スマホからの受付を担当し、その設定やサービスは変更しない。SSH はこのホスト内の直接呼び出しには不要。SSH の認証失敗を設定変更で回避しない。

### 契約内利用の確認（2026-10-16）

`auth status --json` で既存の claude.ai / firstParty / Pro または Max を確認する。続けて、検証済み版 2.1.301 の組み込み `/usage` を画面読み取りモードの一時TTYで読む。既存の信頼済み chezmoi ディレクトリを使い、入力は `/usage` だけ。新しい信頼・ログイン・購入ダイアログには答えない。実モデル用の作業ディレクトリは別の空ディレクトリなので、chezmoi の内容はモデルに渡さない。

契約内使用率が100%未満で、画面に `Usage credits are off` と明記され、診断セッションのモデル使用が0である場合だけ通す。last-known、rate limit、エラー、表示形式変更、版変更、35秒のtimeoutは終了値78で停止する。読み取った値は直後の一回だけに使い、保存済み確認や解除フラグで再利用しない。追加使用の無効状態はアカウント側の表示で確認し、購入コマンドを隠すだけでは代用しない。別端末での設定変更とは原子的ではないため、確認後5秒以内に開始し、実行中にクレジットを有効化しない。

診断TTYと実行プロセスは終了時に回収する。Remote Control はこのプロセスだけの設定で無効にし、永続設定ファイルには書かない。CLI更新で確認済み版から変わったら、読み取り仕様を再確認するまで停止する。

`claude-usage --refresh` は課金確認に使わない。既存実装はモデルを一回呼んでヘッダを得るため、無課金の読み取り確認ではない。Max の表示、`allowed` キャッシュ、`total_cost_usd`、`--max-budget-usd` や追加購入コマンドの非表示も、追加課金がないことの証拠にはしない。

### 準備と回収

一時ファイルは `/tmp`、ユーザーに残す成果物は既存の該当プロジェクト内に置く。新しい作業を始める前に既存の Linear issue を確認し、該当する場合だけ紐付ける。会話履歴・リポジトリ全体・認証情報は自動収集しない。下の `context` には読み直した非機密の抜粋だけを入れる。真偽値は記録であり、秘密の自動検知や権限証明ではない。

```json
{
  "objective": "失敗した小さな論点を一つ記す",
  "scope": "変更・提案してよい範囲を記す",
  "context": "必要な非機密コード・再現条件だけを記す",
  "acceptance": "期待する結果と検証条件を記す",
  "reason": "仮説を変えても進展しなかった理由を記す",
  "attempts": [
    {"failure": "同じエラーA", "change": "試した仮説1"},
    {"failure": "同じエラーA", "change": "試した仮説2"}
  ],
  "authorization": "allowed",
  "non_confidential": true,
  "safety_status": "clear",
  "linear_issue": "既存の該当issueがあれば記す"
}
```

```sh
claude-delegate prepare --task /tmp/task.json --out /tmp/claude-handoff-001
# 保存した task.json と prompt.txt を確認する。
claude-delegate check
# check はモデルを呼ばない。run は保存した check 結果を使わず再確認する。
claude-delegate run --dir /tmp/claude-handoff-001 --timeout 120
# 課金確認に失敗した場合: state=blocked / model_started=false / 終了値78。
```

準備済みディレクトリは上書きしない。課題が変わったら新しいディレクトリで準備し直す。試行は排他マーカーで一回に限り、停止・失敗・承認拒否の後に自動再実行しない。

課金ゲートの先は、空の一時ディレクトリで既存 CLI を起動する。ファイル展開・全ツール・MCP・スキル・hooks を無効にし、モデルと effort は指定しない。安全設定を緩和する権限フラグは使わない。渡したテキストからの分析と提案だけを求め、実装・適用・テストの実行は Sol 側が元の権限内で行う。

回収物は `status.json`（プロセス終了値、timeout、拒否、失敗）、`stdout.json`、`stderr.txt`、`result.json`（回答・提案・未解決点）、`proposed.patch`（未適用の差分）。`suggested_tests` は検証案で、テスト結果ではない。`tests_executed` は常に false。Sol は提案をレビューし、許可範囲内だけを適用し、実際に走らせた検証のコマンド・終了値・出力を別途報告する。Claude の自己申告やプロセス終了値0だけで解決済みにしない。

承認待ち・安全上の拒否・権限不足は、別モデルで迂回しない。Claude が契約切れ・枠切れ・課金条件不明ならそこで止める。重要な未解決部分だけを Astra Max 用の一問に絞り、必要性と追加コストの不確実性を提示して、明示承認後に限って進める。このヘルパーに Astra 起動機能はない。

### 検証

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/claude-delegate.py
```

テストは fake CLI とテスト内の課金ゲート差替えを使う。本番 CLI に mock / force オプションはない。受け渡し、構造化回答・差分回収、終了値、エラーJSON、権限拒否、timeout、課題差替え、二重実行、課金不明・古い確認・版変更時の停止を検証する。課金画面のparserとTTYの受け渡しもmockで検証し、テストから実モデルや認証ファイルには触れない。実動確認の記録は mock 結果と分ける。

仕様: [プログラムからの呼び出し](https://code.claude.com/docs/en/headless)、[費用と契約内利用](https://code.claude.com/docs/en/costs)、[追加使用クレジット](https://support.claude.com/en/articles/12429409-manage-usage-credits-for-paid-claude-plans)。

### 2026-10-16 の実動確認

mock 18件の成功後、chezmoi の対象CLIだけを diff → dry-run → apply し、正本と配置先のSHA-256一致、適用後diffなしを確認した。既存gateway・SSH・認証・安全設定は変更していない。

13:28:23 UTC に呼び出し直前の `/usage` で契約内残枠と追加使用オフ、診断モデル使用0を確認。非機密の架空 `parse` 関数を一回だけ送信し、既定 Opus 5.5 の実回答・構造化結果・提案差分とプロセス終了0を回収した。構造化出力処理を含むCLI内部ターン数は2、課題送信は一回。Claude にリポジトリ読取・編集・テスト実行はさせていない。

呼び出し側が提案差分を確認し、使い捨て環境に適用した。適用前の契約テストが失敗することを確認し、適用後の5件が成功した。これは架空コードでの引き継ぎ検証であり、本番プロジェクトの修正や MusePass hotfix の再開ではない。Astra は起動していない。

証拠は `/home/tsuyoshi/Documents/Codex/2026-10-16/task-4/real-smoke-run/` の `status.json`、`result.json`、`proposed.patch`、`caller-tests.json`、`caller-tests.txt`。`status.json` の `tests_executed=false` はClaude自身の実行範囲を表し、呼び出し側の検証は `caller-tests.json` に分けて記録している。
