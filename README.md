# dotfiles

個人的な設定ファイルを [chezmoi](https://www.chezmoi.io/) で管理するリポジトリです。
**3台のマシン (macOS 1台 + Arch系 Linux 2台) を単一ソースで管理**しており、
OS / ホスト名によるテンプレート分岐が中核機構です。Linux は主に CachyOS
(Archベース) 向けで、EndeavourOS でもそのまま利用可能 (いずれも `ID_LIKE=arch`)。

## マシン構成

| ホスト | OS / WM | テーマ (色分離) | 分岐条件 |
|---|---|---|---|
| mac (M1) | macOS | Gruvbox Material (緑) | `eq .chezmoi.os "darwin"` |
| am5-itx | Arch系 (CachyOS) / Hyprland | Hybrid (青) | デフォルト (`else`) |
| fp7-e14 | Arch系 / Hyprland (常時稼働) | Catppuccin Mocha (紫) | `eq .chezmoi.hostname "fp7-e14"` |

3台のテーマは CIEDE2000 で色相の被りが無いことを確認して選定
(どのマシンの画面かが色で即座に分かる)。パレットは `.chezmoidata/data.yaml` に集約。

## セットアップ

前提: テンプレートが `onepasswordRead` を使うため **1Password CLI (`op`) の
インストールとサインインが必要** (無いと初回 apply がレンダリングで失敗します)。

```bash
# chezmoi のインストール
paru -S chezmoi          # Arch/EndeavourOS
brew install chezmoi     # macOS

# 1Password CLI にサインインしてから
chezmoi init --apply nagamine-git
```

- Linux では `pkglist.txt` のパッケージが `run_onchange_setup.sh` により自動導入されます
- 開発時は `pre-commit install` を推奨 (gitleaks / shellcheck 等がコミット時に走る)

### 更新

```bash
chezmoi apply -v
```

## 構成ハイライト

- **シェル**: zsh + sheldon + starship (2行プロンプト、`starship.toml.tmpl` で3台配色分岐)
- **ターミナル**: Ghostty (UDEV Gothic 35NFLG / リガチャ無効 / カーソル点滅無効)
- **tmux**: prefix は **`C-t`**。TPM (tmux-power / resurrect / continuum / fzf / tilit)。
  pane 数で main-vertical (≤3) ⇔ tiled (≥4) を自動切替 (`M-Enter` でトグル、`M-m` で zoom)
- **Neovim**: leader は **Space**。VSCode 相当の操作系 + 認知科学ベースの UI 設定
  (詳細は下表)。キーの学習は nvim 内で **`:Tutor chezmoi-keys`**

| 機能 | プラグイン | キー |
|---|---|---|
| ファイルツリー | neo-tree | `C-n` |
| ファイル/全文検索 | telescope | `C-p` / `C-f` |
| ソース管理 (diff) | diffview | `Space gg` |
| パンくず | dropbar | (常時表示) |
| 補完 | blink.cmp | `Tab` / `CR` |
| ラベルジャンプ | flash | `s` + 2文字 |
| 問題パネル | trouble | `Space xx` |
| Git ハンク操作 | gitsigns | `]c` `[c` `Space gs` |

## Wolow Companion (Linux のみ)

iPhone の Wolow アプリからの遠隔電源制御 daemon。
`50-wolow-companion.rules` (polkit) / `install.sh` / `uninstall.sh` が部品で、
`run_onchange_setup.sh` から自動導入されます (macOS では `.chezmoiignore` で全て除外)。

バイナリ `wolow-companion` は **git 管理外** (2026-07 にバイナリ直コミットを廃止)。
導入済みマシンは `/usr/local/bin/wolow-companion` の既存コピーで動き続けます。
新規マシンでは既存機からバイナリを取得してから apply:

```bash
scp am5-itx:/usr/local/bin/wolow-companion ~/wolow-companion && chezmoi apply
```

## マシン追加チェックリスト

1. `.chezmoidata/data.yaml` に配色パレットを追加 (既存3台と CIEDE2000 で色相分離を確認)
2. hostname 分岐を持つファイルに分岐を追加:
   `private_dot_config/nvim/init.lua.tmpl` / `dot_tmux.conf.tmpl` /
   `private_dot_config/starship.toml.tmpl` / `private_dot_config/hypr/hyprland.conf.tmpl` /
   `private_dot_ssh/config.tmpl` / `run_onchange_fp7-sleep-mask.sh.tmpl` (該当時)
3. `pkglist.txt` と `.chezmoiignore` の OS 分岐を確認
4. `chezmoi apply --dry-run -v` で差分を確認してから適用

## 復元手順 (新規機・被災機)

1. chezmoi と 1Password CLI を導入し `op` にサインイン
2. `chezmoi init --apply nagamine-git`
3. Linux: 再ログイン (Hyprland / systemd user unit 反映)。tmux は初回起動時に
   TPM がプラグインを自動導入
4. `~/.config/zeed/claude-budget.json` 等の mutable state は chezmoi 管理外
   (必要なら旧機から手動コピー)

### claude-pace (Claude Max 残量計)

`~/.local/bin/claude-pace` は ccusage の active 5h block を読み、loop 司令塔が
配車数を動的調整するための JSON を 1 行出力します (要: jq, ccusage):

```bash
$ claude-pace
{"pct":33,"output_tokens":231220,"budget":700000,"recommend":"scale-up","block_end":"2026-06-11T18:00:00.000Z","remaining_min":184}
```

- `recommend`: scale-up (<60%) / hold (60-80%) / throttle (80-95%、軽作業のみ) / pause (>95%)
- 予算は `~/.config/zeed/claude-budget.json` の `output_budget_5h` (無ければ 700k output tokens / 5h)。
  limit hit 時に司令塔が実測 outputTokens を `hits` 配列へ追記して自動較正します
  (このファイルは司令塔が書き換える mutable state なので chezmoi 管理外)
- Cockpit 可視化は新 endpoint 不要 — 司令塔が wake ごとに
  `https://telemetry.zeed.run/v1/agent-status` へ POST します
  (`agent_id: local:claude-usage`, `kind: background`, `state: running`,
  detail 例「窓 38% (out 270k/700k) · scale-up」)。詳細はスクリプト先頭のコメント参照。

### tuigreet
/etc/greetd/config.toml
```bash
[terminal]
# The VT to run the greeter on. Can be "next", "current" or a number
# designating the VT.
vt = 1

[initial_session]
command = "hyprland"
user = "tsuyoshi"

# The default session, also known as the greeter.
[default_session]

# `agreety` is the bundled agetty/login-lookalike. You can replace `/bin/sh`
# with whatever you want started, such as `sway`.
command = "agreety --cmd hyprland"

# The user to run the command as. The privileges this user must have depends
# on the greeter. A graphical greeter may for example require the user to be
# in the `video` group.
user = "tsuyoshi"
```

<!-- TODO: 調子悪い -->

## iPhone から Hyprland に RDP（Sunshine + Moonlight over Tailscale）

Hyprland は Wayland(wlroots) なので従来の xrdp は使えません。代わりに低遅延ストリーミング
（Sunshine ホスト + Moonlight クライアント）を Tailscale 経由で使います。

### 構成

- ホスト: `sunshine` (pkglist に含む、systemd user service で常駐)
- 設定: `~/.config/sunshine/{sunshine.conf,apps.json}` を chezmoi で配布
- キャプチャ方式: KMS (`cap_sys_admin` は `run_onchange_setup.sh` で付与)
- ネットワーク: Tailscale IP に直接バインド。追加のポート開放は不要
- 仮想ディスプレイ: `~/.local/bin/sunshine-virtual-display.sh` が Hyprland の
  `HEADLESS-*` 出力を生成/破棄（ノート PC の蓋を閉じた状態でも接続可）

### 初回セットアップ

1. `chezmoi apply -v` で設定を反映（`sunshine.service` が有効化される）
2. Tailscale IP を確認: `tailscale ip -4`
3. ブラウザで `https://<tailscale-ip>:47990` を開き、管理者アカウントを作成
4. iPhone に [Moonlight](https://apps.apple.com/app/moonlight-game-streaming/id1000551566) をインストール
5. Moonlight で「Add Host Manually」→ Tailscale IP (または MagicDNS 名) を入力
6. Sunshine Web UI の PIN を Moonlight から入力してペアリング

### 使い方

- `Desktop`: 既存の Hyprland セッションをそのままミラー
- `Hyprland (virtual display)`: 仮想ディスプレイを生やしてから接続（蓋閉じ・外出中向け）
- `Terminal (ghostty)`: ghostty だけを起動して接続

### トラブルシュート

- 接続できない: `tailscale status` と `systemctl --user status sunshine` を確認
- 画面が真っ黒: `setcap` が失敗している可能性。`getcap $(which sunshine)` で
  `cap_sys_admin+p` が付いているか確認
- 音が出ない: `sunshine.conf` の `audio_sink` を `pactl list short sinks` の出力に合わせる

# Kali

## 初期セットアップ
```bash
sudo mkdir -p /etc/distrobox
echo "DBX_CONTAINER_HOME_PREFIX=$HOME/distrobox" | sudo tee /etc/distrobox/distrobox.conf
sudo usermod -aG docker $USER
sudo systemctl start docker
distrobox create --name kali --image docker.io/kalilinux/kali-rolling:latest --home ~/distrobox/kali --additional-flags "--privileged"
distrobox enter kali
export GTK_IM_MODULE=fcitx
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y kali-linux-large locales firefox-esr git dnsutils tor proxychains4
cp /etc/proxychains4.conf ~/.proxychains.conf
sudo systemctl enable tor
```

check ip and tor
```bash
curl -s https://httpbin.org/ip
curl -s https://check.torproject.org/api/ip
```

## 日本語環境セットアップ（推奨）
文字化け防止と日本語表示のため：

```bash
# Kaliコンテナ内で実行
distrobox enter kali

# 日本語ロケール生成
sudo sed -i 's/# ja_JP.UTF-8 UTF-8/ja_JP.UTF-8 UTF-8/' /etc/locale.gen
sudo locale-gen
sudo update-locale LANG=ja_JP.UTF-8

# 日本語フォントインストール
sudo apt update
sudo apt install -y fonts-noto-cjk fonts-noto-color-emoji

# 日本語入力環境設定（<ffffffff>文字化け対策）
echo 'export GTK_IM_MODULE=xim' >> ~/.zshrc
echo 'export QT_IM_MODULE=xim' >> ~/.zshrc
echo 'export XMODIFIERS=@im=fcitx' >> ~/.zshrc
source ~/.zshrc
exit

# コンテナ再起動で設定適用
distrobox enter kali
```

## 権限修正（必要に応じて）
distrobox作成後、一部のアプリケーション（Wiresharkなど）で権限エラーが発生する場合：

```bash
# ホストシステムで実行
sudo chown -R $USER:$USER $HOME/distrobox/kali/.config
sudo chown -R $USER:$USER $HOME/distrobox/kali/.java
```
