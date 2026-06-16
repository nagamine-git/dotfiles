#!/usr/bin/env bash
# ~/bin/hypr_perfmodeswitch.sh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=dot_local/bin/lib_hypr_perfmode.sh
source "$SCRIPT_DIR/lib_hypr_perfmode.sh"

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

  # 弱 GPU (iGPU 等) では Zenzai (Vulkan/llama.cpp GPU offload) が SIGILL でクラッシュ
  # するため、要求が True でもディスクリート GPU が無ければ強制 False に落とす。
  # 判定閾値は hyprland.conf.tmpl の端末振り分けと同一 (NVIDIA/Radeon RX/Navi/Arc=強)。
  # lspci が空 (検出不能) のときは誤って無効化せず要求値を尊重する。
  if [[ "$enable_zenzai" == "True" ]]; then
    local vga
    vga=$(lspci 2>/dev/null | grep -iE 'VGA|3D|Display' || true)
    if [[ -n "$vga" ]] && ! printf '%s' "$vga" | grep -iqE 'NVIDIA|Radeon RX|Navi [0-9]|Arc [AB][0-9]'; then
      enable_zenzai="False"
      logger -t hypr-perfmode "weak GPU detected: Zenzai を強制 OFF (要求=True)" 2>/dev/null || true
    fi
  fi

  if [[ -f "$fcitx5_config" ]]; then
    # 設定ファイルのバックアップを作成（初回のみ）
    [[ ! -f "${fcitx5_config}.backup" ]] && cp "$fcitx5_config" "${fcitx5_config}.backup"

    # ZenzaiEnabled を上書き。行が無ければ追記（fcitx5 GUI が行ごと消すことがあるため）
    if grep -q '^ZenzaiEnabled=' "$fcitx5_config"; then
      sed -i "s/^ZenzaiEnabled=.*/ZenzaiEnabled=$enable_zenzai/" "$fcitx5_config"
    else
      printf '\nZenzaiEnabled=%s\n' "$enable_zenzai" >> "$fcitx5_config"
    fi

    # fcitx5に設定をリロードさせる
    if command -v fcitx5-remote >/dev/null 2>&1; then
      fcitx5-remote -r >/dev/null 2>&1 || true
    fi
  fi
}

if [[ -f $state_file ]]; then
  # 通常モードへ戻す
  hyprctl --batch "$HYPR_NORMAL_BATCH"
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
  hyprctl --batch "$HYPR_PERFORMANCE_BATCH"
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
