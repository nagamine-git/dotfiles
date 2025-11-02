#! /bin/bash

# Stop on error
set -eu

# 汎用インストール関数
install_if_missing() {
  local cmd=$1
  local name=${2:-$1}
  local install_cmd=$3
  
  if ! command -v "$cmd" &> /dev/null; then
    echo "Installing $name..."
    eval "$install_cmd"
  else
    echo "$name already installed, skipping"
  fi
}

# keyboard layout
sudo cp etc/keyd/default.conf /etc/keyd/default.conf

# bbr
# Enable BBR congestion control algorithm
echo "net.core.default_qdisc=fq" | sudo tee /etc/sysctl.d/99-bbr.conf
echo "net.ipv4.tcp_congestion_control=bbr" | sudo tee -a /etc/sysctl.d/99-bbr.conf

# Apply se
# 1password
curl -sS https://downloads.1password.com/linux/keys/1password.asc | gpg --import

# Install packages
paru -S --needed --noconfirm - < ~/pkglist.txt || echo "Some packages failed to install"

# フォント設定
sudo mkdir -p /usr/share/fonts

# Firgeフォントche
if [ ! -f /usr/share/fonts/Firge35NerdConsole-Regular.ttf ]; then
    echo "Firgeフォントをインストールしています..."
    
    # GitHub APIを使用して最新バージョンを取得
    LATEST_RELEASE_INFO=$(curl -s https://api.github.com/repos/yuru7/Firge/releases/latest)
    FIRGE_VERSION=$(echo $LATEST_RELEASE_INFO | grep -o '"tag_name": "[^"]*' | cut -d'"' -f4 | sed 's/^v//')
    
    if [ -z "$FIRGE_VERSION" ]; then
        echo "最新バージョンの取得に失敗しました。デフォルトバージョンを使用します。"
        FIRGE_VERSION="0.3.0"
    else
        echo "最新バージョン ${FIRGE_VERSION} を使用します。"
    fi
    
    wget -O /tmp/firge.zip "https://github.com/yuru7/Firge/releases/download/v${FIRGE_VERSION}/FirgeNerd_v${FIRGE_VERSION}.zip"
    mkdir -p /tmp/firge
    unzip -o /tmp/firge.zip -d /tmp/firge
    sudo cp /tmp/firge/FirgeNerd_v${FIRGE_VERSION}/*.ttf /usr/share/fonts/
    rm -rf /tmp/firge /tmp/firge.zip
    fc-cache -f -v
else
    echo "Firgeフォントはすでにインストールされています。スキップします。"
fi

# RobotoNotoSansJP
if [ ! -f /usr/share/fonts/Roboto-NotoSansJP-Regular.ttf ]; then
    echo "RobotoNotoSansJPフォントをインストールしています..."
    [ -d /tmp/robotonoto ] && rm -rf /tmp/robotonoto
    git clone --depth 1 https://github.com/reindex-ot/RobotoNotoSansJP.git /tmp/robotonoto
    sudo cp /tmp/robotonoto/*.ttf /usr/share/fonts/
    rm -rf /tmp/robotonoto
    fc-cache -f -v
else
    echo "RobotoNotoSansJPフォントはすでにインストールされています。スキップします。"
fi

# アプリケーションのインストール
install_if_missing starship starship "curl -sS https://starship.rs/install.sh | sh"
install_if_missing sheldon sheldon "curl --proto '=https' -fLsS https://rossmacarthur.github.io/install/crate.sh | bash -s -- --repo rossmacarthur/sheldon --to ~/.local/bin --force"

# droidcam
sudo dkms autoinstall
sudo modprobe -r v4l2loopback
sudo modprobe v4l2loopback devices=1 exclusive_caps=1 card_label="DroidCam 1920" max_width=1920 max_height=1080

# gh extension
gh extension install HikaruEgashira/gh-q
ghq get HikaruEgashira/gh-q

# tmux
git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm

# bluetooth
echo "Enabling Bluetooth service..."
sudo systemctl enable --now bluetooth
sudo usermod -a -G bluetooth $USER

