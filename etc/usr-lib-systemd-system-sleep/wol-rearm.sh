#!/bin/sh
# systemd-sleep(8) hook: suspend 直前に WoL を再 arm。
# ドライバによっては suspend で wol 設定が落ちることがあるため。
case "$1" in
  pre)
    /usr/bin/ethtool -s enp9s0 wol g 2>/dev/null || true
    ;;
esac
