# Debian セットアップガイド

## 目次
- [初期セットアップ](#初期セットアップ)
- [パッケージリポジトリの設定](#パッケージリポジトリの設定)
- [カスタマイズ](#カスタマイズ)
  - [SWAP設定](#swap設定)

---

## 初期セットアップ

キーボードレイアウトを設定し、ユーザー権限を追加します：

```bash
# Colemakレイアウトの設定
setxkbmap us -variant colemak ctrl:swapcaps

# 管理者権限の追加
su -
sudo usermod -aG sudo tsuyoshi
sudo reboot
```

## パッケージリポジトリの設定

パッケージリポジトリを設定し、最新カーネルをインストールします：

```bash
# /etc/apt/sources.list を編集
sudo vi /etc/apt/sources.list
```

以下の内容に変更します：

```
# Security updates
deb http://security.debian.org/debian-security bookworm-security main contrib non-free non-free-firmware
deb-src http://security.debian.org/debian-security bookworm-security main contrib non-free non-free-firmware

# Stable repository
deb http://ftp.riken.jp/Linux/debian/debian bookworm main contrib non-free non-free-firmware
deb-src http://ftp.riken.jp/Linux/debian/debian bookworm main contrib non-free non-free-firmware

# Stable updates
deb http://ftp.riken.jp/Linux/debian/debian bookworm-updates main contrib non-free non-free-firmware
deb-src http://ftp.riken.jp/Linux/debian/debian bookworm-updates main contrib non-free non-free-firmware

# Stable backports
deb http://ftp.riken.jp/Linux/debian/debian bookworm-backports main contrib non-free non-free-firmware
deb-src http://ftp.riken.jp/Linux/debian/debian bookworm-backports main contrib non-free non-free-firmware
```

backportsリポジトリを追加し、最新カーネルをインストールします：

```bash
sudo sh -c 'echo "deb http://deb.debian.org/debian $(lsb_release -cs)-backports main contrib non-free" > /etc/apt/sources.list.d/backports.list'
sudo apt update

# 最新カーネルのインストール
sudo apt install linux-image-6.12.9+bpo-amd64
sudo update-grub
sudo reboot
```

基本ツールとchezmoiをインストールします：

```bash
sudo apt install curl git
sh -c "$(wget -qO- get.chezmoi.io)"
bin/chezmoi init
```

## カスタマイズ

### SWAP設定

パフォーマンス向上のためにSWAPファイルを設定します：

```bash
sudo fallocate -l 16G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapoff -a
sudo swapon /swapfile
```

> **注意**: /tmp ディレクトリは再起動時に消去されるため、再ビルドが必要な場合は最初からやり直す必要があります。
