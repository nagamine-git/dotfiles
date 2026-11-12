#!/usr/bin/env bash
# waybar の custom/disk。/ の使用率を点字のメーター (⡀..⣿ の 8 段) で返す。
# 旧版は 44% で満杯の表示になり、色の状態も使用率の数字も出なかった。
# 0–100% を 8 段に等分し、80% で warning、90% で critical のクラスを付け、ツールチップに数字を出す。
set -eu

read -r used total < <(df -P / | awk 'NR==2 {print $3, $2}')
perc=$(( used * 100 / total ))
icons=(⡀ ⣀ ⣄ ⣤ ⣦ ⣶ ⣷ ⣿)
idx=$(( perc * 8 / 100 ))
[ "$idx" -gt 7 ] && idx=7

class=""
if [ "$perc" -ge 90 ]; then
  class="critical"
elif [ "$perc" -ge 80 ]; then
  class="warning"
fi

used_g=$(( used / 1024 / 1024 ))
total_g=$(( total / 1024 / 1024 ))
printf '{"text":"%s","tooltip":"ディスク (/): %s%% 使用 (%s / %s GiB)","class":"%s","percentage":%s}\n' \
  "${icons[$idx]}" "$perc" "$used_g" "$total_g" "$class" "$perc"
