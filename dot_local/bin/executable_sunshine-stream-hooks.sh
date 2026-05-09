#!/usr/bin/env bash
# Sunshine の prep-cmd フック。ストリーム接続中は新規 idle lock がかからないようにする。
# 既にロック中の hyprlock には絶対に触らない (kill すると ext-session-lock-v1 が壊れて
# Hyprland が "lockscreen app died" safety screen に落ちるため)。
# ロック中に繋いだ場合は Moonlight のソフトキーボードでパスワード入力して解除する。
set -u

LOG=/tmp/sunshine-stream-hooks.log
log() { printf "[%s] %s\n" "$(date '+%F %T')" "$*" >>"$LOG" 2>/dev/null || true; }

stop_idle() { pkill -x hypridle 2>/dev/null || true; }

start_idle() {
  pgrep -x hypridle >/dev/null && return 0
  setsid -f hypridle </dev/null >/dev/null 2>&1 || hypridle >/dev/null 2>&1 &
  disown 2>/dev/null || true
}

case "${1:-}" in
  on)
    log "stream on: suspend hypridle (existing hyprlock left untouched)"
    stop_idle
    ;;
  off)
    log "stream off: resume hypridle"
    start_idle
    ;;
  *)
    echo "usage: $0 on|off" >&2
    exit 64
    ;;
esac
