#!/bin/sh
# 毎晩 02:00 に systemd timer から呼ばれる。
# - /home/tsuyoshi/.no-suspend-tonight があれば 1 回限りスキップ (翌朝起こす分も無し)。
# - 無ければ rtcwake で次の 06:30 に RTC アラーム仕込んで suspend。
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
WAKE_HHMM=06:30

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

WAKE_TS=$(date -d "today $WAKE_HHMM" +%s)
NOW_TS=$(date +%s)
if [ "$WAKE_TS" -le "$NOW_TS" ]; then
  WAKE_TS=$(date -d "tomorrow $WAKE_HHMM" +%s)
fi

logger -t nightly-suspend "arming RTC wake at $(date -d "@$WAKE_TS") then suspending"
/usr/bin/rtcwake -m no -t "$WAKE_TS"
/usr/bin/systemctl suspend
