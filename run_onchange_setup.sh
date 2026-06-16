#! /bin/bash

# Stop on error
set -eu

# chezmoi の run_ スクリプトは CWD = $HOME で実行されるので、
# `etc/...` のような相対パスでソース内のファイルを参照するには
# まず chezmoi の source dir に移動する必要がある。
cd "${CHEZMOI_SOURCE_DIR:-$HOME/.local/share/chezmoi}"

# Windowsと時刻が合わないので、システム時刻をUTCに変更する
timedatectl set-local-rtc 1 --adjust-system-clock

# 汎用インストール関数
install_if_missing() {
  local cmd=$1
  local name=${2:-$1}
  local install_cmd=$3
 
  if ! command -v "$cmd" &> /dev/null; then
    echo "Installing $name..."
    # 個別 install の失敗で setup 全体 (set -e) を巻き込まない。
    # 1 ツールが入らなくても後続のシステム設定・サービス有効化は続行させる。
    eval "$install_cmd" || echo "⚠ $name のインストールに失敗 (継続)"
  else
    echo "$name already installed, skipping"
  fi
}

# keyboard layout
sudo cp etc/keyd/default.conf /etc/keyd/default.conf

# === 据置きデスクトップ専用の電源管理 (形状で自動振り分け) ===
# nightly-suspend (夜間 rtcwake) と Wake-on-LAN は「据置き・有線・後で起こす」前提。
# ノパソ (バッテリあり) は蓋閉じ/標準の電源管理に任せるのでスキップ。
# バッテリ有無で判定するので、新マシンも自動で正しく振り分く。
if ls /sys/class/power_supply/BAT* >/dev/null 2>&1; then
  echo "→ laptop 検出: 据置き電源管理 (nightly-suspend / WoL) はスキップ"
else
  echo "→ desktop 検出: nightly-suspend + WoL を設定"
  # nightly suspend (02:00 JST -> rtcwake 06:30) — atuin/Claude ログで「100% 寝てる」帯
  sudo install -m 755 etc/usr-local-sbin/nightly-suspend.sh /usr/local/sbin/nightly-suspend.sh
  sudo install -m 644 etc/systemd/system/nightly-suspend.service /etc/systemd/system/nightly-suspend.service
  sudo install -m 644 etc/systemd/system/nightly-suspend.timer /etc/systemd/system/nightly-suspend.timer
  sudo systemctl daemon-reload
  sudo systemctl enable --now nightly-suspend.timer

  # Wake-on-LAN — 有線IF を動的検出 (enp9s0 ベタ書きをやめ、別NICの新デスクトップにも追従)。
  # LAN 内からは wakeonlan で起こせる。
  ETH_IF=$(ip -o link show | awk -F': ' '/: (en|eth)/{print $2; exit}')
  if [ -n "$ETH_IF" ]; then
    sudo install -m 644 etc/systemd/system/wol-enable.service /etc/systemd/system/wol-enable.service
    sudo install -m 755 etc/usr-lib-systemd-system-sleep/wol-rearm.sh /usr/lib/systemd/system-sleep/wol-rearm.sh
    # 検出した IF をインストール済みファイルへ反映 (etc/ の既定 enp9s0 を置換)
    sudo sed -i "s/enp9s0/$ETH_IF/g" \
      /etc/systemd/system/wol-enable.service \
      /usr/lib/systemd/system-sleep/wol-rearm.sh
    sudo systemctl daemon-reload
    sudo systemctl enable --now wol-enable.service
  else
    echo "  (有線IF が見つからないため WoL はスキップ)"
  fi
fi

# === sleep / lid 設定 (システム必須。壊れやすい install 群より前に置く) ===
# パッケージや npm の失敗で電源・lid 設定がブロックされないよう、setup の冒頭側で確実に適用する。
# (以前はファイル末尾にあり、openclaw の EACCES で set -e 中断 → 永久に未適用だった)
sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true
sudo mkdir -p /etc/systemd/logind.conf.d
sudo cp etc/systemd/logind.conf.d/lid-action.conf /etc/systemd/logind.conf.d/lid-action.conf
# NOTE: logind は restart しない。稼働中の Wayland コンポジタ (Hyprland) は DRM/input
# デバイスを logind 経由で握っており、logind 再起動でアクセスを失い画面が tty へフォール
# バックして壊れる。lid-action.conf は次回ブート時に自然に反映される (急ぐなら手動 reboot)。

# === Wolow Companion (iPhone Wolow アプリからの遠隔電源制御 daemon) ===
# install.sh が冪等にバイナリ/systemd service/polkit を設置し enable --now する。
# 同梱バイナリは x86-64 ビルドなのでアーキを確認。失敗しても setup は止めない。
if [ "$(uname -m)" = "x86_64" ] && [ -f ./install.sh ]; then
  bash ./install.sh || echo "⚠ wolow-companion install 失敗 (継続)"
fi

# bbr
# Enable BBR congestion control algorithm
echo "net.core.default_qdisc=fq" | sudo tee /etc/sysctl.d/99-bbr.conf
echo "net.ipv4.tcp_congestion_control=bbr" | sudo tee -a /etc/sysctl.d/99-bbr.conf

# 1password
curl -sS https://downloads.1password.com/linux/keys/1password.asc | gpg --import

# Install packages
# pkglist.txt は chezmoi ソース管理下の正本を使う（CWD は冒頭で source dir に移動済み）。
# 以前は管理外の ~/pkglist.txt を読んでいて、リポジトリと乖離したまま放置される地雷だった。
paru -S --needed --noconfirm - < pkglist.txt || echo "Some packages failed to install"

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
# システム npm の global prefix (/usr/lib/node_modules) は root 権限が要るため sudo。
# 失敗しても install_if_missing 側で握りつぶし継続する。
install_if_missing openclaw openclaw "sudo npm i -g openclaw"

# droidcam
# v4l2loopback-dkms 未ビルド/未ロードでも setup 全体を止めない（set -e 対策で || true）。
sudo dkms autoinstall || true
sudo modprobe -r v4l2loopback 2>/dev/null || true
sudo modprobe v4l2loopback devices=1 exclusive_caps=1 card_label="DroidCam 1920" max_width=1920 max_height=1080 || true

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

# Tailscale SSH を有効化（sshd 不要で tailnet 経由ログイン可能に。新マシンを最初から
# リモート管理できる）。`set` は他の設定を温存（`up` と違いクロバーしない）。
# 未ログイン時は静かにスキップし、Tailscale 認証後の再実行で有効になる。
sudo tailscale set --ssh 2>/dev/null || true

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

# === 壁紙: 無ければ DL (冪等) ===
# 環境心理学エビデンスで最上位の構図 (霧の湖×山×鏡面反射 / blue space + mystery + calm)。
# Hyprland はタイル WM でデスクトップアイコンが無いため overlay 等は不要。hyprpaper が参照する。
WALLPAPER_DIR="$HOME/.local/share/wallpaper"
WALLPAPER="$WALLPAPER_DIR/wallpaper.jpg"
if [ ! -f "$WALLPAPER" ]; then
  echo "壁紙をダウンロードしています..."
  mkdir -p "$WALLPAPER_DIR"
  curl -fsSL "https://unsplash.com/photos/dGyshquBzOc/download?force=true&w=3840" \
    -o "$WALLPAPER" || echo "⚠ 壁紙のダウンロードに失敗 (継続)"
else
  echo "壁紙は既に存在します。スキップします。"
fi
