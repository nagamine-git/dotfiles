#!/usr/bin/env bash
# waybar の custom/notification。swaync の状態の流れ (swaync-client -swb) を受け取り、
# 未読が 0 件のときは数字を出さない。ツールチップに操作の案内を出す。
set -u

swaync-client -swb | jq --unbuffered -c '
  ((.text | tonumber?) // 0) as $n
  | (.alt // "" | startswith("dnd")) as $dnd
  | .text = (if $n > 0 then " \($n)" else "" end)
  | .tooltip = ((if $n > 0 then "未読の通知 \($n) 件" else "未読の通知なし" end)
      + (if $dnd then " (サイレントモード中)" else "" end)
      + "\n\nクリック / Super+R: 通知センター\n中クリック: すべて消す\n右クリック: サイレントモードの切替")'
