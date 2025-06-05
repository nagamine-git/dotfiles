# dotfiles

個人的な設定ファイルを[chezmoi](https://www.chezmoi.io/)で管理するリポジトリです。
主にEndeavourOS（Archベース）向けに最適化されています。

## 主な設定

- ディストリビューション: EndeavourOS / Arch Linux
- シェル: Zsh + Starship
- ウィンドウマネージャ: Hyprland
- ターミナル: foot
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
vt = 1

[default_session]
# command = "tuigreet -t -r --remember-session --asterisks --cmd hyprland"
command = "agreety -c hyprland"
user    = "tsuyoshi"
```

# Kali

## 初期セットアップ
```bash
sudo mkdir -p /etc/distrobox
echo "DBX_CONTAINER_HOME_PREFIX=$HOME/distrobox" | sudo tee /etc/distrobox/distrobox.conf
sudo usermod -aG docker $USER
sudo systemctl start docker
distrobox create --name kali --image docker.io/kalilinux/kali-rolling:latest --home ~/distrobox/kali --additional-flags "--privileged"
distrobox enter kali
sudo apt update && sudo apt install -y locales
sudo apt full-upgrade -y
sudo apt install -y kali-linux-default
sudo apt install -y kali-linux-large
kali-tweaks
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