#!/bin/sh
# 毎晩 02:00 に systemd timer から呼ばれる。
# - /home/tsuyoshi/.no-suspend-tonight があれば 1 回限りスキップ (翌朝起こす分も無し)。
# - 無ければ rtcwake で次の 06:30 に RTC アラーム仕込んで suspend。
# 02-06 時の活動が atuin/Claude のログ上ゼロな前提のデータドリブン設計。
set -eu

USER_HOME=/home/tsuyoshi
SKIP_FLAG="$USER_HOME/.no-suspend-tonight"
WAKE_HHMM=06:30

if [ -f "$SKIP_FLAG" ]; then
  rm -f "$SKIP_FLAG"
  logger -t nightly-suspend "skip flag consumed; not suspending tonight"
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
