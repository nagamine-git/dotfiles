# ChatGPT のメモリ上限 (chatgpt-launch)

am5-itx では、ChatGPT を `~/.local/bin/chatgpt-launch` から起動する。
このスクリプトが、ChatGPT が自分で作る app scope にメモリ上限を付ける。
ChatGPT が膨らんだときに、システム全体の OOM で別のアプリが巻き込まれないようにするためである。
上限を超えたときは、ChatGPT だけが減速するか終了する。

## 上限を付ける入口は am5-itx の 3 か所

次の 3 か所が chatgpt-launch を通す。ほかの経路 (端末で `command chatgpt` を直接実行するなど) で起動した ChatGPT には上限が付かない。

- **ログイン時の起動**:`private_dot_config/hypr/hyprland.lua.tmpl` の am5-itx の条件の中。
- **desktop entry**:`dot_local/share/applications/chatgpt.desktop.tmpl`。Vicinae のアプリ検索と `codex://` の URI ハンドラーもこれを使う。
- **zsh の `chatgpt`**:`dot_zshrc`。`~/.local/bin/chatgpt-launch` があるときだけ使う。

上限の値は am5-itx で測ったものなので、ほかのホストには `.chezmoiignore` でスクリプトを置かない。
ほかのホストの desktop entry と zsh は、`chatgpt --ozone-platform=wayland` を直接起動する。

## 仕組み

ChatGPT (Chromium) は起動後に自分で `app-*.scope` を作り、メイン process をそこへ移す。
`systemd-run --scope` で包んでも、移った時点で元の scope は空になり、上限は残らない (使い捨ての scope で確認済み)。
そこで chatgpt-launch は、`--watch-chatgpt <pid>` を裏で走らせてから `exec` で ChatGPT に置き換わる。
`exec` なので pid は変わらない。watcher は `app-*-<pid>.scope` が現れたら、`systemctl --user set-property --runtime` で上限を付ける。

この scope には、メイン process と、その後に生む Codex・MCP サーバー・その Chrome が入る。
zygote 経由の子 (renderer や GPU など) の大半は上限の対象外になる。
tmux から起動していたときは、これらが元の tmux pane の scope に残ることを確かめた。
直接起動する今は、起動元 (Hyprland など) の cgroup に残ると考えられるが、まだ確かめていない。

## 値と通知

- **値**:High 16 GiB / Max 24 GiB / SwapMax 8 GiB。根拠の実測 (2026-10-28、am5-itx) はスクリプト冒頭のコメントにある。
- **High を超えたとき**:ChatGPT だけが減速し、swap へ回収される。
- **Max を超えたとき**:`OOMPolicy=stop` により scope ごと終了する。Codex のセッションも止まる。
- **通知**:High と Max それぞれの 90% で、一度ずつ `notify-send` する。上限を付けられなかったときも通知する。
- **付け直し**:付与は runtime だけなので、ChatGPT を起動するたびに付け直す。起動済みの ChatGPT には、次の起動まで効かない。
- **起動済みのとき**:URI と focus を ChatGPT の single-instance の処理へ渡すだけで、watcher は作らない。

## 確認

テストは使い捨ての HOME と、偽物の ChatGPT・systemctl・notify-send・pgrep を使う。実際のアプリや systemd には触らない。

```sh
bash -n dot_local/bin/executable_chatgpt-launch
shellcheck dot_local/bin/executable_chatgpt-launch
python3 tests/chatgpt-launch.py
python3 tests/desktop-autostart.py
chezmoi diff ~/.config/hypr/hyprland.lua ~/.local/share/applications/chatgpt.desktop ~/.local/bin/chatgpt-launch ~/.zshrc
```
