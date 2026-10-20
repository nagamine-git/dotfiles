#! /bin/bash

# Stop on error
set -eu

# chezmoi の run_ スクリプトは CWD = $HOME で実行されるので、
# `etc/...` のような相対パスでソース内のファイルを参照するには
# まず chezmoi の source dir に移動する必要がある。
cd "${CHEZMOI_SOURCE_DIR:-$HOME/.local/share/chezmoi}"

# Windowsと時刻が合わないので、システム時刻をUTCに変更する
# 設定済みなら触らない (polkit 認証待ちでタイムアウトし set -e で setup 全体が止まるため)
[ "$(timedatectl show -p LocalRTC --value 2>/dev/null)" = yes ] || sudo timedatectl set-local-rtc 1 --adjust-system-clock

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
# Wake-on-LAN は「据置き・有線・後で起こす」前提。
# ノパソ (バッテリあり) は蓋閉じ/標準の電源管理に任せるのでスキップ。
# バッテリ有無で判定するので、新マシンも自動で正しく振り分く。
#
# 2026-08-26 に自動 suspend を恒久廃止したため nightly-suspend の設置を削除した。
# ここには install + `systemctl enable --now nightly-suspend.timer` が書かれており、
# 手で timer を disable しても chezmoi apply のたびに復活する状態だった。
if ls /sys/class/power_supply/BAT* >/dev/null 2>&1; then
  echo "→ laptop 検出: 据置き電源管理 (WoL) はスキップ"
else
  echo "→ desktop 検出: WoL を設定"
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

# === OOM対策: zram 16GB + systemd-oomd (am5-itx専用, 2026-08-29) ===
# 2026-08-29、zeed(ブラウザ自動化)×9 + ffmpeg 18.6GB のメモリスパイクを
# swap0Bのまま食らい、kernelのoom-killerが即発動して複数プロセス
# (tmux pane・slack含む) が巻き添え死 → reboot に至った ([[project_tmux_oom_reboot]])。
# zramで瞬間スパイクの緩衝材を作り、systemd-oomdで「1プロセスだけ早期に狩る」
# 体制にする。Arch の systemd は Fedora と違い oomd 有効化の drop-in を同梱しないため
# -.slice / user-.slice を自前で ManagedOOM 化しないと oomd は何も監視しない。
if [ "$(hostname)" = "am5-itx" ]; then
  echo "→ am5-itx 検出: zram 16GB×2 + systemd-oomd を設定"
  sudo pacman -S --needed --noconfirm zram-generator
  sudo install -D -m 644 etc/systemd/zram-generator.conf /etc/systemd/zram-generator.conf
  sudo install -D -m 644 "etc/systemd/system/-.slice.d/10-oomd-root-slice-defaults.conf" "/etc/systemd/system/-.slice.d/10-oomd-root-slice-defaults.conf"
  sudo install -D -m 644 etc/systemd/system/user-.slice.d/10-oomd-user-slice-defaults.conf /etc/systemd/system/user-.slice.d/10-oomd-user-slice-defaults.conf
  sudo systemctl daemon-reload
  # zram1 は 2026-09-06 追加 (zram0 満杯対策)。既存 zram0 はサイズ変更せず起動のみ
  sudo systemctl start systemd-zram-setup@zram0.service systemd-zram-setup@zram1.service
  sudo systemctl enable --now systemd-oomd.service

  # === sched-ext (scx_bpfland): 重い処理中の入力遅延対策 (am5-itx, 2026-09-06) ===
  # linux-cachyos は sched_ext 対応だが既定では無効 (/sys/kernel/sched_ext/state = disabled)。
  # scx_loader.service で bpfland を載せる (scx.service は廃止済み)。`systemctl stop scx_loader` で即座に既定へ戻る。
  sudo pacman -S --needed --noconfirm scx-scheds scx-tools
  sudo install -D -m 644 etc/scx_loader/config.toml /etc/scx_loader/config.toml
  sudo rm -f /etc/default/scx
  sudo systemctl disable --now scx.service 2>/dev/null || true
  sudo systemctl enable --now scx_loader.service

  # === アイドル省電力: EPP balance_power (am5-itx, 2026-09-22) ===
  # 上限 (PPT / GPU cap / scaling_max_freq) は変えず、アイドル〜軽負荷の周波数選択だけ省電力寄りにする。
  # /etc/tmpfiles.d/cpu-epp.conf は以前からあったが power-profiles-daemon (balanced =
  # balance_performance) が起動後に上書きしていた。ppd は依存元なし・powerprofilesctl も壊れて
  # いたので mask する。戻すときは `systemctl unmask --now power-profiles-daemon`。
  sudo install -D -m 644 etc/tmpfiles.d/cpu-epp.conf /etc/tmpfiles.d/cpu-epp.conf
  sudo systemctl disable --now power-profiles-daemon.service 2>/dev/null || true
  sudo systemctl mask power-profiles-daemon.service
  sudo systemd-tmpfiles --create /etc/tmpfiles.d/cpu-epp.conf
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
curl -sS https://downloads.1password.com/linux/keys/1password.asc | gpg --import || echo "⚠ 1password GPG key import 失敗 (継続)"

# Install packages
# pkglist.txt は chezmoi ソース管理下の正本を使う（CWD は冒頭で source dir に移動済み）。
# 以前は管理外の ~/pkglist.txt を読んでいて、リポジトリと乖離したまま放置される地雷だった。
# コメント(#…)と空行を除去してから渡す。paru/pacman は stdin の '#' を
# パッケージ名扱いするため、生の pkglist.txt を流すと "# security" 等で誤爆する。
# pkglist で入れ替えたパッケージ (旧:新)。衝突は --noconfirm だと「N」になり一括インストール全体が失敗するので、
# 公式リポジトリの新パッケージに替えるものは先に旧を外す。
replaced_pkgs=(waybar-git:waybar)
for pair in "${replaced_pkgs[@]}"; do
  old="${pair%%:*}"; new="${pair##*:}"
  if pacman -Q "$old" >/dev/null 2>&1 && ! pacman -Q "$new" >/dev/null 2>&1; then
    sudo pacman -Rdd --noconfirm "$old" && sudo pacman -S --needed --noconfirm "$new" || echo "⚠ $old → $new の入れ替えに失敗 (継続)"
  fi
done
mapfile -t pkgs < <(grep -vE '^[[:space:]]*(#|$)' pkglist.txt)
if ! paru -S --needed --noconfirm "${pkgs[@]}"; then
  # 1 つの衝突・ビルド失敗で他まで入らないのを防ぐため、1 つずつ入れ直す
  echo "⚠ 一括インストールに失敗。1 つずつ入れ直す"
  for pkg in "${pkgs[@]}"; do
    paru -S --needed --noconfirm "$pkg" >/dev/null 2>&1 || echo "  ⚠ $pkg のインストールに失敗 (継続)"
  done
fi

# 既に zsh なら chsh (パスワード入力) を求めない
[ "$(getent passwd "$USER" | cut -d: -f7)" = "$(command -v zsh)" ] || chsh -s "$(command -v zsh)"

mise i || echo "⚠ mise i 失敗 (継続)"


# アプリケーションのインストール
# droidcam
# v4l2loopback-dkms 未ビルド/未ロードでも setup 全体を止めない（set -e 対策で || true）。
sudo dkms autoinstall || true
sudo modprobe -r v4l2loopback 2>/dev/null || true
sudo modprobe v4l2loopback devices=1 exclusive_caps=1 card_label="DroidCam 1920" max_width=1920 max_height=1080 || true

# gh extension
# gh extension install HikaruEgashira/gh-q
# gh extension install dlvhdr/gh-dash
# ghq get HikaruEgashira/gh-q


# bluetooth
echo "Enabling Bluetooth service..."
sudo systemctl enable --now bluetooth
# 今の bluez は 'bluetooth' グループを作らない (polkit 管理)。存在する環境だけ追加し、
# 無い環境で usermod が exit 6 → setup.sh 全体を失敗させるのを防ぐ。
getent group bluetooth >/dev/null && sudo usermod -a -G bluetooth "$USER"

# systemctl
sudo systemctl enable --now keyd
sudo systemctl enable --now greetd
sudo systemctl enable --now tailscaled
# pkglist/README で謳っている IRQ 分散を実際に有効化 (長年 inactive だった)
sudo systemctl enable --now irqbalance

# tailscale operator設定（sudo無しでtailscale CLI/taildropを使えるように）
sudo tailscale set --operator="$USER" 2>/dev/null || true

# Tailscale SSH を有効化（sshd 不要で tailnet 経由ログイン可能に。新マシンを最初から
# リモート管理できる）。`set` は他の設定を温存（`up` と違いクロバーしない）。
# 未ログイン時は静かにスキップし、Tailscale 認証後の再実行で有効になる。
sudo tailscale set --ssh 2>/dev/null || true

# パッケージ更新後に tailscaled とクライアントのバージョンがずれるのを防ぐ自動更新。
# pacman 管理など自動更新が使えない環境ではエラーを無視して何もしない。
sudo tailscale set --auto-update 2>/dev/null || true

# === ファイアウォール: firewalld に一本化 ===
# Tailscale は認証済みなので trusted。物理LAN側は既定拒否を維持する。
# Wolow Companion (無認証の電源操作, 20388) は Tailscale 経由だけで使うので LAN には開けない。
# 通常の SSH は Tailscale SSH を使う。
# firewalld が入って起動してから ufw を止める (先に止めるとファイアウォール無しの時間ができる)。
if sudo pacman -S --needed --noconfirm firewalld && sudo systemctl enable --now firewalld.service; then
  sudo systemctl disable --now ufw.service 2>/dev/null || true
  sudo firewall-cmd --permanent --zone=trusted --add-interface=tailscale0
  sudo firewall-cmd --permanent --zone=public --remove-service=ssh 2>/dev/null || true
  sudo firewall-cmd --permanent --zone=public --remove-port=20388/tcp 2>/dev/null || true
  sudo firewall-cmd --permanent --zone=public --remove-port=20388/udp 2>/dev/null || true
  sudo firewall-cmd --reload
else
  echo "⚠ firewalld を有効化できないため ufw のまま (要確認)"
fi

# taildrop auto-receiver (systemd user service)
systemctl --user daemon-reload
systemctl --user enable --now taildrop.service 2>/dev/null || true

# === 週次セキュリティ更新チェック (checkupdates + arch-audit → claude-notify) ===
systemctl --user enable --now security-update-check.timer 2>/dev/null || true

# === Btrfsスナップショット ===
# pacman更新の前後を snap-pac が自動保存し、grub-btrfs がGRUBへ反映する。
# snapper はパッケージ導入 (paru) が失敗すると入っていないので、無ければスキップする
if [ "$(findmnt -no FSTYPE / 2>/dev/null)" = "btrfs" ] && command -v snapper >/dev/null 2>&1; then
  if ! sudo snapper -c root get-config >/dev/null 2>&1; then
    sudo snapper -c root create-config /
  fi
  sudo systemctl enable --now snapper-timeline.timer snapper-cleanup.timer
  sudo systemctl enable --now grub-btrfsd.service
fi

# 対応デバイスのファームウェア情報を定期更新する（更新適用自体は確認して手動）。
sudo systemctl enable --now fwupd-refresh.timer 2>/dev/null || true

# === am5-itx の旧パッケージ整理 ===
# CachyOSを通常用、LTSを復旧用として残す。ブラウザと言語処理系は用途があるため温存。
if [ "$(hostname)" = "am5-itx" ]; then
  stale_packages=(
    electron39 electron40 electron43
    yay-bin fuzzel wofi helix niri timeshift ufw
    linux linux-headers linux-zen linux-zen-headers
    glances neofetch duf meld wavemon psensor evhz-git hyprsession-sh # 未使用 CLI / GUI
    nano nano-syntax-highlighting gperf efitools pkgfile ngrok python-pipx # 未使用 CLI / GUI
    netctl xl2tpd modemmanager usb_modeswitch b43-fwcutter dnsmasq haveged ntp iwd # NetworkManager + wpa_supplicant 構成で未使用のネットワーク関連
    sg3_utils lsscsi nilfs-utils jfsutils f2fs-tools xfsprogs dmraid # 未使用のファイルシステム・ストレージツール
    welcome eos-apps-info eos-log-tool eos-quickstart eos-packagelist reflector-simple # EndeavourOS の GUI 残骸
    xorg-xinit xorg-xkill xorg-xdpyinfo xf86-video-ati # X11 残骸
    rust # pacman の rust (rustup と mise に一本化済み。共存すると rust-analyzer が壊れる)
  )
  installed_stale=()
  for package in "${stale_packages[@]}"; do
    pacman -Q "$package" >/dev/null 2>&1 && installed_stale+=("$package")
  done
  if [ "${#installed_stale[@]}" -gt 0 ]; then
    sudo pacman -Rns --noconfirm "${installed_stale[@]}"
    sudo grub-mkconfig -o /boot/grub/grub.cfg
  fi

  # 上の削除で孤立した依存パッケージも片付ける。
  mapfile -t orphans < <(pacman -Qdtq || true)
  if [ "${#orphans[@]}" -gt 0 ]; then
    sudo pacman -Rns --noconfirm "${orphans[@]}"
  fi

  # 導入済みパッケージは直近2世代だけ残し、削除済みパッケージのキャッシュは全消去。
  sudo paccache -r -k 2
  sudo paccache -ruk 0
fi

# === 壁紙: 昼/夜の2枚を DL (冪等)。darkman が日の出/日没で自動切替 ===
# 昼= 霧の湖 (明るい/blue space + calm)、夜= 焚き火+星空 (暗い/暖色 = 低メラノピック)。
# 実切替は ~/.local/share/{light,dark}-mode.d/wallpaper.sh (darkman フック) が行う。
# hyprpaper はアクティブな wallpaper.jpg を参照。Hyprland はタイル WM なので overlay 不要。
WALLPAPER_DIR="$HOME/.local/share/wallpaper"
mkdir -p "$WALLPAPER_DIR"
[ -f "$WALLPAPER_DIR/wallpaper-day.jpg" ] || \
  curl -fsSL "https://unsplash.com/photos/dGyshquBzOc/download?force=true&w=3840" \
    -o "$WALLPAPER_DIR/wallpaper-day.jpg" || echo "⚠ 昼壁紙のDL失敗 (継続)"
[ -f "$WALLPAPER_DIR/wallpaper-night.jpg" ] || \
  curl -fsSL "https://images.unsplash.com/photo-1722641277067-a7fba0ad1a59?q=85&fm=jpg&w=3840" \
    -o "$WALLPAPER_DIR/wallpaper-night.jpg" || echo "⚠ 夜壁紙のDL失敗 (継続)"
# 現在の darkman モードでアクティブ壁紙を決定 (取得不可なら昼)
if [ "$(darkman get 2>/dev/null)" = "dark" ] && [ -f "$WALLPAPER_DIR/wallpaper-night.jpg" ]; then
  cp -f "$WALLPAPER_DIR/wallpaper-night.jpg" "$WALLPAPER_DIR/wallpaper.jpg"
elif [ -f "$WALLPAPER_DIR/wallpaper-day.jpg" ]; then
  cp -f "$WALLPAPER_DIR/wallpaper-day.jpg" "$WALLPAPER_DIR/wallpaper.jpg"
fi

# 壁紙の上部輝度に合わせて waybar を明/暗テーマ化 (colors.css は create_ で初回のみ既定 dark を作るため、初回 apply 後に再適用)
if [ -x "$HOME/.local/bin/waybar-auto-theme.sh" ]; then
  "$HOME/.local/bin/waybar-auto-theme.sh" || true
fi

# === 2026-07 監査クリーンアップ (冪等。全機で一巡したら削除してよい) ===
# 旧世代 brave-browser.desktop の配備残骸 (ソースは削除済み、~/.local/share 版に一本化)
rm -f "$HOME/.config/brave-browser.desktop"
# Continue.dev 廃止 (Claude Code に一本化。設定・同期 skill とも撤去)
rm -rf "$HOME/.continue"
# Ghostty CVE-2026-26982 (ペースト経由の任意コマンド実行、v1.3.0 で修正) の未対応検出
if command -v ghostty >/dev/null 2>&1; then
  gv="$(ghostty +version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  if [ -n "$gv" ] && [ "$(printf '%s\n' 1.3.0 "$gv" | sort -V | head -1)" != "1.3.0" ]; then
    echo "⚠ ghostty $gv は CVE-2026-26982 未修正 (>=1.3.0 必要)。更新を推奨"
  fi
fi
