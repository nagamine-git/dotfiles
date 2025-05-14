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
# sudo apt install linux-image-6.12.9+bpo-amd64
# 最新かつリアルタイムカーネル
sudo apt install linux-image-6.12.22+bpo-rt-amd64 linux-headers-6.12.22+bpo-rt-amd64
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

```bash
# bash --version > 5.0.0
./setup.sh
```

<details>
<summary>4l2loopbackを使ったDroidCam仮想カメラの設定方法</summary>

## うまくいく設定のまとめ

1. **正しいバージョンのインストール**:
```bash
sudo apt update
sudo apt install -t bookworm-backports v4l2loopback-dkms v4l2loopback-utils
```

## 事前準備：DKMSビルド

```bash
sudo apt update
sudo apt install -t bookworm-backports linux-image-amd64
sudo apt install -y linux-headers-amd64 build-essential dkms
sudo dkms autoinstall
```

2. **モジュールのロード設定**:
```bash
sudo modprobe -r v4l2loopback || true
sudo modprobe v4l2loopback exclusive_caps="1" card_label="DroidCam Virtual Camera" video_nr=4 max_width=1280 max_height=720
```

3. **必要なパラメータ**:
- `exclusive_caps=1`: 必須（カメラとして認識されるようにする）
- `video_nr=4`: デバイス番号固定
- `max_width=1280 max_height=720`: 初期解像度（動作確認済み）

4. **パーミッション設定**:
```bash
# ユーザーをvideoグループに追加
sudo usermod -a -G video $USER
echo 'KERNEL=="video[0-9]*", GROUP="video", MODE="0660"' | sudo tee /etc/udev/rules.d/83-v4l2loopback.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

5. **設定ファイルの作成**:
```bash
sudo bash -c 'cat > /etc/modprobe.d/v4l2loopback.conf << EOF
options v4l2loopback exclusive_caps=1 card_label="DroidCam Virtual Camera" video_nr=4 max_width=1280 max_height=720
EOF'
```

6. **フレームレート設定**:
```bash
v4l2-ctl -d /dev/video4 -p 60
```

## 高画質設定（安定したら）

```bash
sudo modprobe -r v4l2loopback || true
sudo modprobe v4l2loopback exclusive_caps=1 card_label="DroidCam Virtual Camera" video_nr=4 max_width=1920 max_height=1080 max_buffers=32

sudo bash -c 'cat > /etc/modprobe.d/v4l2loopback.conf << EOF
options v4l2loopback exclusive_caps=1 card_label="DroidCam Virtual Camera" video_nr=4 max_width=1920 max_height=1080 max_buffers=32
EOF'

v4l2-ctl -d /dev/video4 -p 60
```

## トラブルシューティング
- 動作しない場合は、解像度を下げる（1280x720）
- `lsmod | grep v4l2` でモジュールが正しくロードされているか確認
- `v4l2-ctl --list-devices` でデバイスが正しく認識されているか確認
- `stat /dev/video4` でパーミッションを確認（グループが「video」になっているか）

重要なポイントは、正しいバージョン（0.13.2-1）、解像度設定、exclusive_caps=1パラメータの使用、そして適切なパーミッション設定です。

</details>


## Kali lxd

```bash
# ホスト側：LXD のインストールと初期化（1回だけ）
sudo apt update
sudo apt install -y snapd
sudo snap install lxd --classic
sudo lxd init --auto

# X ソケットを許可
xhost +local:

# LXD デバイスとして X ソケットを追加（一度だけで OK）
lxc config device add kali X0 disk source=/tmp/.X11-unix path=/tmp/.X11-unix

# Kali コンテナを初回起動
lxc launch images:kali/rolling kali

# コンテナ内でパッケージを入れる
lxc exec kali -- bash -c "apt update && apt install -y kali-linux-large"
```

```bash
# ホスト側：X ソケットを許可
xhost +local:

# コンテナが停止中なら起動
if ! lxc info kali | grep -q "Status: Running"; then
  lxc start kali
fi

# コンテナに入りたいだけなら exec
lxc exec kali -- /bin/bash
```