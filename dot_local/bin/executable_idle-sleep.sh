#!/usr/bin/env bash
# Called by hypridle on long idle timeout.
# Hibernates only when running on battery (laptop unplugged).
# Does nothing on desktop (no battery) or laptop on AC.
set -euo pipefail

on_battery() {
  local f
  for f in /sys/class/power_supply/BAT*/status; do
    [[ -r "$f" ]] || continue
    [[ "$(< "$f")" == "Discharging" ]] && return 0
  done
  return 1
}

on_battery && exec systemctl hibernate
