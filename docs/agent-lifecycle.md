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
