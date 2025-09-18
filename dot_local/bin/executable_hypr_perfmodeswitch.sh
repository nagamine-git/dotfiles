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
fcitx5_config="$HOME/.config/fcitx5/conf/hazkey.conf"

# fcitx5のZenzai設定を変更する関数
toggle_fcitx5_zenzai() {
  local enable_zenzai=$1
  
  if [[ -f "$fcitx5_config" ]]; then
    # 設定ファイルのバックアップを作成（初回のみ）
    [[ ! -f "${fcitx5_config}.backup" ]] && cp "$fcitx5_config" "${fcitx5_config}.backup"
    
    # ZenzaiEnabledの値を変更
    sed -i "s/^ZenzaiEnabled=.*/ZenzaiEnabled=$enable_zenzai/" "$fcitx5_config"
    
    # fcitx5に設定をリロードさせる
    if command -v fcitx5-remote >/dev/null 2>&1; then
      fcitx5-remote -r >/dev/null 2>&1 || true
    fi
  fi
}

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
    keyword misc:vfr true;
    keyword misc:animate_manual_resizes true;
  "
  # powerprofilesctl set balanced  # Disabled due to missing dependencies
  # Set CPU governor to schedutil (adaptive)
  if [[ -w /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]]; then
    echo schedutil | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor >/dev/null 2>&1
  fi
  
  # fcitx5のZenzai機能を有効化（通常モード）
  toggle_fcitx5_zenzai "True"
  
  rm -f "$state_file"
  notify-send "Hyprland" "🌈 通常モード (Zenzai: ON)"
else
  # 高速モードへ
  hyprctl --batch "
    keyword animations:enabled false;
    keyword decoration:blur:enabled false;
    keyword decoration:shadow:enabled false;
    keyword decoration:rounding 0;
    keyword decoration:active_opacity 1;
    keyword decoration:inactive_opacity 1;
    keyword general:border_size 6;
    keyword render:max_fps 60;
    keyword general:gaps_in 0;
    keyword general:gaps_out 0;
    keyword decoration:multisample_edges false;
    keyword cursor:animate false;
    keyword misc:vrr off;
    keyword misc:vfr false;
    keyword misc:animate_manual_resizes false;
  "
  # powerprofilesctl set performance  # Disabled due to missing dependencies
  # Set CPU governor to performance
  if [[ -w /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]]; then
    echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor >/dev/null 2>&1
  fi
  
  # fcitx5のZenzai機能を無効化（パフォーマンスモード）
  toggle_fcitx5_zenzai "False"
  
  touch "$state_file"
  notify-send "Hyprland" "🚀 高速モード ON (Zenzai: OFF)"
fi
