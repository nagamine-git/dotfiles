# ChatGPT / Codex の tmux 起動

`am5-itx` の Hyprland 自動起動と ChatGPT desktop entry は、同じ
`desktop-apps-tmux` を使う。新しい対話型 Codex CLI は追加しない。
GUI 初回起動と既存 `codex app-server daemon start` を専用 tmux server から実行する。
既存 GUI への URI / focus は、アプリの single-instance 処理へ渡す。
daemon の lifecycle、登録、listen 設定は変更しない。daemon は起動後に独立するため、
starter が tmux 内にあることを、daemon や SSH 承認対象の保持と同一視しない。

## 認証と環境

現行 `.zshrc` の `op signin` はコメントアウトされ、tmux 設定には active な op 呼び出しがない。
このラッパーは `op run` / `inject` / `signin`、SSH 接続、署名、権限変更を行わない。
既存 `SSH_AUTH_SOCK` と GUI の必要な環境変数だけを新しい server に渡す。
OP セッショントークン・service-account token・API key の環境注入は行わない。
専用 control socket と lock はユーザー所有の `XDG_RUNTIME_DIR` 配下の 0700 directory に置く。
共有の `.tmux.conf` や resurrect / continuum plugin を読み込まない。
最後の pane 終了時に専用 server は終了し、アプリの自動再起動は行わない。

tmux の session environment 更新は、新しい pane に適用される。起動済みアプリの
Wayland / DBus 環境を更新するものではない。ログアウト後の GUI 継続は保証しない。
1Password が認識する承認対象と承認再利用の効果は未検証。

## source と反映

- `private_dot_config/hypr/hyprland.conf.tmpl`: 既存 am5-itx 条件内の二つの起動を一つへ統合。
- `dot_local/share/applications/chatgpt.desktop.tmpl`: am5-itx だけ wrapper を選択。URI/MIME を保持。
- `dot_local/bin/executable_desktop-apps-tmux`: 引数を shell 展開せず直接渡し、role ごとの lock を使用。
- `private_dot_config/desktop-apps/tmux.conf`: 専用 server の最小設定。
- `.chezmoiignore`: wrapper/config を他ホストでは配置しない。

```sh
bash -n dot_local/bin/executable_desktop-apps-tmux
python3 tests/desktop-apps-tmux.py
shellcheck dot_local/bin/executable_desktop-apps-tmux
chezmoi diff --exclude=scripts ~/.config/hypr/hyprland.conf ~/.local/share/applications/chatgpt.desktop ~/.local/bin/desktop-apps-tmux ~/.config/desktop-apps/tmux.conf
chezmoi apply --dry-run --force --exclude=scripts ~/.config/hypr/hyprland.conf ~/.local/share/applications/chatgpt.desktop ~/.local/bin/desktop-apps-tmux ~/.config/desktop-apps/tmux.conf
```

上の `--force` は、変更済み実ファイルの TTY 確認を省く dry-run 専用。実 apply に付けない。
既存の正本・実ファイルとの差分を先に保存する。対象限定でも Hyprland 全ファイルの
未反映変更が含まれるため、今回以外の差分があれば本人へ提示し、無断で反映しない。
認可された反映時だけ、同じ四対象を指定して `chezmoi apply --exclude=scripts` を行う。
起動中 GUI / daemon の kill・restart・ログアウトや `exec-once` の手動実行は別途タイミングを確認する。

## 試験と復元

テストは使い捨て HOME、偽物の ChatGPT / Codex / op / ssh と合成データを使う。
実 tmux の試験も専用 test socket と偽物アプリだけで行い、その server だけを片付ける。
通常の SSH 要求や 1Password の解除は発生しない。
反映後の GUI 表示、自然に必要になった URI 転送、再ログインと承認対象は別途確認する。

復元は変更前に保存した正本と実ファイルを戻し、新規 wrapper/config だけを除く。
未コミット変更や untracked desktop entry があるため、`git restore HEAD` は使わない。
復元前にも今回の変更後からの追加編集がないか確認する。共有 tmux server や稼働 daemon を止めない。
