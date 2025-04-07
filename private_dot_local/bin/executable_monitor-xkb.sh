#!/bin/bash

set -eu

XKB_SCRIPT="$HOME/.local/bin/apply-custom-xkb.sh"
LOG_FILE="$HOME/.xkb_monitor.log"
CURRENT_DATE=$(date "+%Y-%m-%d %H:%M:%S")

# スクリプトの存在確認
if [ ! -f "$XKB_SCRIPT" ]; then
    echo "[$CURRENT_DATE] ERROR: XKB script does not exist at $XKB_SCRIPT" >> "$LOG_FILE"
    # スクリプトが存在しない場合、chezmoi applyで復元
    chezmoi apply "$HOME/.local/bin/apply-custom-xkb.sh"
    echo "[$CURRENT_DATE] Restored XKB script using chezmoi" >> "$LOG_FILE"
fi

# スクリプトの実行権限確認
if [ ! -x "$XKB_SCRIPT" ]; then
    echo "[$CURRENT_DATE] ERROR: XKB script is not executable" >> "$LOG_FILE"
    chmod +x "$XKB_SCRIPT"
    echo "[$CURRENT_DATE] Made XKB script executable" >> "$LOG_FILE"
fi

# 現在のキーボード設定を確認
LAYOUT_CHECK=$(setxkbmap -print | grep -i custom || echo "not_found")
if [ "$LAYOUT_CHECK" = "not_found" ]; then
    echo "[$CURRENT_DATE] WARNING: Custom keyboard layout not active. Reapplying..." >> "$LOG_FILE"
    "$XKB_SCRIPT"
    echo "[$CURRENT_DATE] Reapplied custom keyboard layout" >> "$LOG_FILE"
else
    echo "[$CURRENT_DATE] Custom keyboard layout is active" >> "$LOG_FILE"
fi 