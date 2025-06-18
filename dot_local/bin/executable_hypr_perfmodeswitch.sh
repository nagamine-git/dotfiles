#!/usr/bin/env bash
# ~/bin/hypr_perfmodeswitch.sh
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
  "
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
  "
  touch "$state_file"
  notify-send "Hyprland" "🚀 高速モード ON"
fi
