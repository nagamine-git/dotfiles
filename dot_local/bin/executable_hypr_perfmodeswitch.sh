#!/usr/bin/env bash
# ~/bin/hypr_perfmodeswitch.sh
set -euo pipefail

# ---- error handling ----
# Notify and exit if any command fails
error_handler() {
  local exit_code=$?
  local line=${BASH_LINENO[0]}
  notify-send "Hyprland" "⚠️ hypr_perfmodeswitch エラー (行 $line, code $exit_code)"
  exit "$exit_code"
}
trap error_handler ERR

state_file=/tmp/hypr_perf_mode

if [[ -f $state_file ]]; then
  # 通常モードへ戻す
  hyprctl --batch "
    keyword animations:enabled true;
    keyword decoration:blur:enabled true;
    keyword decoration:shadow:enabled true;
    keyword decoration:rounding 8;
    keyword decoration:active_opacity 1;
    keyword decoration:inactive_opacity 0.8;
    keyword general:border_size 1;
    keyword render:max_fps 0;
    keyword general:gaps_in 5;
    keyword general:gaps_out 5;
    keyword decoration:multisample_edges true;
    keyword cursor:animate true;
    keyword misc:vrr on;
  "
  powerprofilesctl set balanced
  rm -f "$state_file"
  notify-send "Hyprland" "🌈 通常モード"
else
  # 高速モードへ
  hyprctl --batch "
    keyword animations:enabled false;
    keyword decoration:blur:enabled false;
    keyword decoration:shadow:enabled false;
    keyword decoration:rounding 0;
    keyword decoration:active_opacity 1;
    keyword decoration:inactive_opacity 1;
    keyword general:border_size 3;
    keyword render:max_fps 60;
    keyword general:gaps_in 0;
    keyword general:gaps_out 0;
    keyword decoration:multisample_edges false;
    keyword cursor:animate false;
    keyword misc:vrr off;
  "
  powerprofilesctl set performance
  touch "$state_file"
  notify-send "Hyprland" "🚀 高速モード ON"
fi
