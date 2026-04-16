#!/usr/bin/env bash
set -euo pipefail

# 現在の exit node
current=$(tailscale status --json 2>/dev/null | jq -r '.ExitNodeStatus.ID // empty')

# 候補リスト（tailnet内の他デバイス + Mullvadノード）
# tailscale exit-node list の出力: IP HOSTNAME COUNTRY CITY STATUS
nodes=$(tailscale exit-node list 2>/dev/null | awk '/^[0-9]/ {print $2}' | sort -u || true)

if [[ -z "$nodes" ]]; then
  notify-send -u low "Tailscale" "利用可能な exit node がありません。\nMullvad を tailscale admin で有効化してください。"
  xdg-open "https://login.tailscale.com/admin/settings/general" >/dev/null 2>&1 || true
  exit 0
fi

header="🚫 None (direct)"
[[ -n "$current" ]] && header="🚫 None (direct) [current: exit enabled]"

choice=$(printf '%s\n%s\n' "$header" "$nodes" | \
  wofi --dmenu --prompt="Exit Node" -i --width=600 --height=500)

[[ -z "$choice" ]] && exit 0

if [[ "$choice" == 🚫* ]]; then
  tailscale set --exit-node=
  notify-send "Tailscale" "Exit node を解除しました"
else
  tailscale set --exit-node="$choice" --exit-node-allow-lan-access
  notify-send "Tailscale" "Exit node: $choice"
fi
