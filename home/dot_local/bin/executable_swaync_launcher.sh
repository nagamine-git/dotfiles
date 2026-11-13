#!/usr/bin/env bash
set -eu

kill_notifier() {
  local name="$1"
  if command -v pgrep >/dev/null 2>&1 && pgrep -x "$name" >/dev/null 2>&1; then
    pkill -x "$name" || true
    local attempts=20
    while pgrep -x "$name" >/dev/null 2>&1 && [ $attempts -gt 0 ]; do
      sleep 0.1
      attempts=$((attempts - 1))
    done
  fi

  if command -v systemctl >/dev/null 2>&1; then
    local unit="${name}.service"
    if systemctl --user is-active --quiet "$unit" >/dev/null 2>&1; then
      systemctl --user stop "$unit" >/dev/null 2>&1 || true
    fi
  fi
}

kill_notifier "swaync"
kill_notifier "mako"
kill_notifier "dunst"

exec swaync "$@"
