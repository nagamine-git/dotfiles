#!/bin/sh
# Enable blue-light-filter via hyprsunset in dark mode
pkill -x hyprsunset 2>/dev/null || true
sleep 0.2
hyprsunset -t 3000 &
