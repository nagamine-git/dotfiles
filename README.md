# dotfiles

個人的な設定ファイルを[chezmoi](https://www.chezmoi.io/)で管理するリポジトリです。
主にEndeavourOS（Archベース）向けに最適化されています。

## 主な設定

- ディストリビューション: EndeavourOS / Arch Linux
- シェル: Zsh + Starship
- ウィンドウマネージャ: Hyprland
- ターミナル: Ghostty
- エディタ: Neovim
- 入力メソッド: fcitx5
- システム最適化: irqbalance, powertop
- 開発ツール: Docker, lazygit, lazydocker, atuin
- その他: git, SSH, waybar など

## 使い方

### インストール

```bash
# chezmoiのインストール
paru -S chezmoi

# リポジトリの取得と適用
chezmoi init --apply nagamine-git
```

### 更新

```bash
# 変更を適用
chezmoi apply -v
```

### パッケージ

必要なパッケージは `pkglist.txt` に記載されており、`run_onchange_setup.sh` 実行時に自動的にインストールされます。

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
