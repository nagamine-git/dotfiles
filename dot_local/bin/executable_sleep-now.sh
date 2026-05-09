#!/usr/bin/env bash
# Manual suspend with explicit WoL info (= 後で起こせる前提のスリープ)。
#
# 使い方:
#   sleep-now              … いつでも誰かが起こすまで寝続ける (WoL 起こし待ち)
#   sleep-now 2h           … 2時間後に RTC アラームで自動起床 (それより前に WoL でも起こせる)
#   sleep-now 07:00        … 次の 07:00 に RTC アラーム
#
# 起こす側コマンド:
#   同じ LAN: wakeonlan 30:56:0f:46:da:f4
#   iPhone Moonlight (家 WiFi 接続中): host 長押し → "Wake PC"
#   ※外出先 (cellular/別 LAN) からの WoL は家側に常時 ON の relay (RPi/router 等) が必要

set -eu

IFACE=enp9s0
MAC=$(ip -o link show "$IFACE" 2>/dev/null | awk -F'link/ether ' 'NF>1 {print $2}' | awk '{print $1}')
WAKE_ARG="${1:-}"

# WoL 状態確認 (root じゃなくても見える)
WOL_STATE=$(sudo /usr/bin/ethtool "$IFACE" 2>/dev/null | awk -F': *' '/Wake-on:/{print $2; exit}' || echo "?")

cat <<EOF
== sleep-now ==
iface : $IFACE
mac   : $MAC
wol   : $WOL_STATE   (g = magic packet 有効)

EOF

if [ -n "$WAKE_ARG" ]; then
  if ! WAKE_TS=$(date -d "$WAKE_ARG" +%s 2>/dev/null); then
    echo "invalid time: $WAKE_ARG" >&2
    exit 64
  fi
  NOW=$(date +%s)
  if [ "$WAKE_TS" -le "$NOW" ]; then
    WAKE_TS=$(date -d "tomorrow $WAKE_ARG" +%s)
  fi
  echo "RTC wake at: $(date -d "@$WAKE_TS" '+%F %T %Z')"
  sudo /usr/bin/rtcwake -m no -t "$WAKE_TS" >/dev/null
fi

if [ "$WOL_STATE" != "g" ]; then
  echo
  echo "WARNING: WoL が $WOL_STATE。LAN からは起こせないかもしれない。"
  echo "  sudo systemctl start wol-enable.service  で arm し直す。"
fi

echo
echo "起こし方:"
echo "  LAN内: wakeonlan $MAC"
echo "  iPhone Moonlight (家WiFi時): host 長押し → Wake PC"
[ -n "$WAKE_ARG" ] && echo "  自動: $(date -d "@$WAKE_TS" '+%F %T') に RTC で自動起床"
echo

read -r -p "suspend する? [Y/n] " a
case "${a:-Y}" in
  y|Y|yes|Yes) systemctl suspend ;;
  *) echo "中止"; exit 0 ;;
esac
