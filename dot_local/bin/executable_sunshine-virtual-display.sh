#!/usr/bin/env bash
# Sunshine から呼ばれる仮想ディスプレイトグル。
# iPhone から接続する際に Hyprland のヘッドレス出力を生やし、
# 接続が切れたら元に戻す。
#
# Usage:
#   sunshine-virtual-display.sh on [WIDTHxHEIGHT@REFRESH]
#   sunshine-virtual-display.sh off
set -eu

ACTION=${1:-on}
MODE=${2:-1920x1080@60}
STATE_FILE=${XDG_RUNTIME_DIR:-/tmp}/sunshine-virtual-display.state

# 物理ディスプレイの既知安定状態。ヘッドレス出力を抜き差しすると Hyprland が
# 全出力の CRTC を再評価して HDMI-A-1 を再 modeset するため、セッション終了時に
# ここへ明示的に戻さないと「真っ暗のまま戻らない」ことがある。
# VRR は 4K@120Hz の HDMI だと追従中にパネルがブランクするため必ずオフに固定。
PHYS_MONITOR="HDMI-A-1,3840x2160@120.0,0x0,1.5"

reassert_physical() {
  hyprctl keyword misc:vrr 0           >/dev/null 2>&1 || true
  hyprctl keyword monitor "$PHYS_MONITOR" >/dev/null 2>&1 || true
  hyprctl dispatch dpms on             >/dev/null 2>&1 || true
}

case "$ACTION" in
  on)
    # 既存のヘッドレス出力を探し、無ければ作る
    headless=$(hyprctl monitors -j | jq -r '.[] | select(.name | startswith("HEADLESS-")) | .name' | head -n1)
    if [ -z "$headless" ]; then
      hyprctl output create headless >/dev/null
      # 生成直後は name が確定しないので再取得
      sleep 0.2
      headless=$(hyprctl monitors -j | jq -r '.[] | select(.name | startswith("HEADLESS-")) | .name' | head -n1)
    fi
    [ -z "$headless" ] && { echo "failed to create headless output" >&2; exit 1; }

    hyprctl keyword monitor "${headless},${MODE},auto,1"
    echo "$headless" > "$STATE_FILE"
    ;;
  off)
    if [ -f "$STATE_FILE" ]; then
      headless=$(cat "$STATE_FILE")
      hyprctl output remove "$headless" >/dev/null || true
      rm -f "$STATE_FILE"
    fi
    # ヘッドレス削除に伴う CRTC 再評価で HDMI が不安定状態へ戻るのを防ぐ
    reassert_physical
    ;;
  *)
    echo "usage: $0 {on|off} [WIDTHxHEIGHT@REFRESH]" >&2
    exit 2
    ;;
esac
