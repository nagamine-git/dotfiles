#!/bin/sh
# 毎晩 02:00 に systemd timer から呼ばれる。
# - /home/tsuyoshi/.no-suspend-tonight があれば 1 回限りスキップ。
# - 無ければ suspend する。自動復帰はしない (2026-07-19 に rtcwake 06:30 を撤去。
#   定刻に勝手に起きるのが不評だったため。起こすときは WoL / Wolow を使う)。
# 02-06 時の活動が atuin/Claude のログ上ゼロな前提のデータドリブン設計。
#
# ガード:
#   1. 時刻ガード: 01-05 時以外は no-op。
#      Persistent=false でも suspend 中に missed した OnCalendar=02:00 が
#      wake 直後に catchup 発火するケースがある (2026-05-25 朝の事故で観測)。
#      昼間に二度目の suspend が走ると dGPU SMU resume が死ぬ。
#   2. uptime ガード: boot/resume 直後 5 分以内は no-op。
#      連続 suspend は xhci / amdgpu が確実に死ぬ。
set -eu

USER_HOME=/home/tsuyoshi
SKIP_FLAG="$USER_HOME/.no-suspend-tonight"

if [ -f "$SKIP_FLAG" ]; then
  rm -f "$SKIP_FLAG"
  logger -t nightly-suspend "skip flag consumed; not suspending tonight"
  exit 0
fi

hour=$(date +%H)
if [ "$hour" -lt 1 ] || [ "$hour" -gt 5 ]; then
  logger -t nightly-suspend "SKIP: out of nightly window (hour=$hour, allowed 01-05)"
  exit 0
fi

uptime_sec=$(awk '{print int($1)}' /proc/uptime)
if [ "$uptime_sec" -lt 300 ]; then
  logger -t nightly-suspend "SKIP: uptime ${uptime_sec}s < 300s (just booted/resumed)"
  exit 0
fi

# 過去に rtcwake で仕込んだアラームが残っていても無効化してから寝る
echo 0 > /sys/class/rtc/rtc0/wakealarm 2>/dev/null || true

logger -t nightly-suspend "suspending (no RTC wake; use WoL to wake)"
/usr/bin/systemctl suspend
