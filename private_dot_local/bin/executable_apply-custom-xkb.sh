#!/bin/bash

set -e

# 簡潔なログだけを記録
LOG_FILE="$HOME/.xkb_setup.log"
echo "XKB setup: $(date)" > $LOG_FILE

# 既存の設定をクリア
setxkbmap -option ""

# カスタムXKBレイアウトを適用
setxkbmap -I$HOME/.local/share/xkb/symbols -layout custom -variant vim -option ""
if [ $? -ne 0 ]; then
    # 失敗した場合はフォールバック
    setxkbmap -layout us -variant colemak -option ctrl:nocaps
    echo "Applied fallback layout" >> $LOG_FILE
else
    echo "Applied custom layout" >> $LOG_FILE
fi
