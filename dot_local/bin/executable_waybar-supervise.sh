#!/usr/bin/env bash
# waybar をクラッシュ時のみ自動再起動する (tray の libdbusmenu SEGV 対策)。
# SIGSEGV(139)/SIGABRT(134)/SIGBUS(135) 以外の終了 (killall 等の意図的停止) では再起動しない。
# 1分以内に5回落ちたら諦める (クラッシュループ防止)。
crashes=()
while true; do
  waybar "$@"
  rc=$?
  case $rc in 134|135|139) ;; *) exit "$rc" ;; esac
  now=$(date +%s)
  crashes=("${crashes[@]}" "$now")
  recent=()
  for t in "${crashes[@]}"; do (( now - t < 60 )) && recent+=("$t"); done
  crashes=("${recent[@]}")
  logger -t waybar-supervise "waybar crashed (rc=$rc), restarting (${#crashes[@]}/5 in 60s)" 2>/dev/null || true
  (( ${#crashes[@]} >= 5 )) && exit "$rc"
  sleep 1
done
