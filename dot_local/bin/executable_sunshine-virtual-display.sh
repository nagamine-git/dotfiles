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
    ;;
  *)
    echo "usage: $0 {on|off} [WIDTHxHEIGHT@REFRESH]" >&2
    exit 2
    ;;
esac
