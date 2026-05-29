#!/usr/bin/env bash
# Simple day/night idle sleep — called by hypridle after 30 min of inactivity.
#
# 規則 (たった 4 つ):
#   1. 09:00–22:59 (service window) は寝ない
#   2. tailnet (100.64.0.0/10) に接続中なら寝ない
#   3. オーディオ再生中なら寝ない
#   4. それ以外 (= 23:00–08:59 で 30 分 AFK) → suspend (ノートはバッテリー時 hibernate)
#
# 過去に smart-idle-score.py / collector / 5 段 listener と heatmap で
# 学習させてみたが、保守コストに見合わなかったので時刻ベースに戻した。
set -euo pipefail

TAG=idle-sleep
hour=$(date +%H)

# Rule 1: service window
if [ "$hour" -ge 9 ] && [ "$hour" -lt 23 ]; then
    logger -t "$TAG" "STAY: service window ($hour:00–23:00)"
    exit 0
fi

# Rule 2: active tailnet TCP (someone reaching us via Tailscale)
if ss -tnH state established 2>/dev/null \
        | awk '$5 ~ /^100\./ {f=1; exit} END {exit !f}'; then
    logger -t "$TAG" "STAY: active tailnet connection"
    exit 0
fi

# Rule 2b: real remote SSH session (Remote=yes; local tmux panes excluded)
remote_n=$(loginctl list-sessions --no-legend 2>/dev/null \
    | awk '{print $1}' \
    | while read -r s; do
        loginctl show-session "$s" -p Remote --value 2>/dev/null
    done | grep -c '^yes$' || true)
if [ "${remote_n:-0}" -gt 0 ]; then
    logger -t "$TAG" "STAY: $remote_n remote session(s)"
    exit 0
fi

# Rule 3: audio / mic actively running (Zoom, mpv, music)
if command -v pactl >/dev/null 2>&1; then
    if pactl list sink-inputs 2>/dev/null \
            | grep -q "^[[:space:]]State: RUNNING"; then
        logger -t "$TAG" "STAY: audio playback"
        exit 0
    fi
    if pactl list source-outputs 2>/dev/null \
            | grep -q "^[[:space:]]State: RUNNING"; then
        logger -t "$TAG" "STAY: microphone in use"
        exit 0
    fi
fi

# Rule 4: suspend (hibernate on battery)
bat_status=""
for f in /sys/class/power_supply/BAT*/status; do
    [ -r "$f" ] && bat_status="$(cat "$f")" && break
done
if [ "$bat_status" = "Discharging" ]; then
    logger -t "$TAG" "HIBERNATE: laptop on battery (hour=$hour)"
    exec systemctl hibernate
fi
logger -t "$TAG" "SUSPEND: hour=$hour, no veto"
exec systemctl suspend
