#!/bin/bash
# Visual blink effect for pomodoro notifications using hyprsunset

COUNT=5
INTERVAL=0.01

for i in $(seq 1 $COUNT); do
  hyprsunset -t 10000 &
  sleep "$INTERVAL"
  pkill -x hyprsunset 2>/dev/null || true

  hyprsunset -t 3000 &
  sleep "$INTERVAL"
  pkill -x hyprsunset 2>/dev/null || true
done

# Restore: re-apply night filter if in rest/dark mode
if [[ "$1" == "--rest" ]]; then
  hyprsunset -t 3000 &
fi
