#! /bin/bash

# Stop on error
set -eu

# Windowsと時刻が合わないので、システム時刻をUTCに変更する
timedatectl set-local-rtc 1 --adjust-system-clock

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

# 1password
curl -sS https://downloads.1password.com/linux/keys/1password.asc | gpg --import

# Install packages
paru -S --needed --noconfirm - < ~/pkglist.txt || echo "Some packages failed to install"

# フォント設定
sudo mkdir -p /usr/share/fonts

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
install_if_missing openclaw openclaw "npm i -g openclaw"

# droidcam
sudo dkms autoinstall
sudo modprobe -r v4l2loopback
sudo modprobe v4l2loopback devices=1 exclusive_caps=1 card_label="DroidCam 1920" max_width=1920 max_height=1080

# gh extension
gh extension install HikaruEgashira/gh-q
gh extension install dlvhdr/gh-dash
ghq get HikaruEgashira/gh-q


# bluetooth
echo "Enabling Bluetooth service..."
sudo systemctl enable --now bluetooth
sudo usermod -a -G bluetooth $USER

# systemctl
sudo systemctl enable --now keyd
sudo systemctl enable --now greetd
sudo systemctl enable --now tailscaled

# tailscale operator設定（sudo無しでtailscale CLI/taildropを使えるように）
sudo tailscale set --operator="$USER" 2>/dev/null || true

# firewalld を使っている場合 tailscale0 を trusted zone に入れる
# (WireGuardで既に認証済みなので全通信を許可)
if systemctl is-active --quiet firewalld; then
  sudo firewall-cmd --permanent --zone=trusted --add-interface=tailscale0 2>/dev/null || true
  sudo firewall-cmd --reload 2>/dev/null || true
fi

# taildrop auto-receiver (systemd user service)
systemctl --user daemon-reload
systemctl --user enable --now taildrop.service 2>/dev/null || true

# Sunshine (iPhone / Moonlight RDP over Tailscale)
# KMS キャプチャに必要な権限を付与し、ユーザ単位の常駐を有効化
if command -v sunshine &> /dev/null; then
  sudo setcap cap_sys_admin+p "$(command -v sunshine)" 2>/dev/null || true
  systemctl --user enable --now sunshine.service 2>/dev/null || true
fi

sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true
sudo mkdir -p /etc/systemd/logind.conf.d
sudo cp etc/systemd/logind.conf.d/lid-action.conf /etc/systemd/logind.conf.d/lid-action.conf

echo 'Search and set to wallpaper = ,~/Pictures/john-towner-JgOeRuGD_Y4-unsplash.jpg'
