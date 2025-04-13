#!/bin/bash
# デバッグをセットアップ
set -e

# ログディレクトリの作成
LOG_DIR="$HOME/.local/log"
mkdir -p "$LOG_DIR"

# デバッグログ
DEBUG_LOG="$LOG_DIR/bizstart_debug.log"
echo "==== $(date) ====" > "$DEBUG_LOG"

# デスクトップエントリを実行
for file in ~/Desktop/startup/*.desktop; do
    if [ -f "$file" ]; then
        # Extract Name from desktop file
        app_name=$(grep -oP '^Name=\K.*' "$file")
        echo "Found desktop file: $file with app_name: $app_name" | tee -a "$DEBUG_LOG"
        
        # Extract base name (remove notification count patterns like (9+))
        base_name=$(echo "$app_name" | sed 's/ *([0-9]\+[+]*)//')
        echo "Base name for search: $base_name" | tee -a "$DEBUG_LOG"
        
        # Check if window with this name already exists
        window_ids=$(xdotool search --name ".*${base_name}.*" 2>/dev/null || echo "")
        
        if [ -z "$window_ids" ]; then
            echo "Starting $app_name..." | tee -a "$DEBUG_LOG"
            xdg-open "$file" > "$LOG_DIR/${app_name// /_}.log" 2>&1 &
        else
            echo "Found window IDs: $window_ids" | tee -a "$DEBUG_LOG"
            echo "Found matching windows:" | tee -a "$DEBUG_LOG"
            for id in $window_ids; do
                window_name=$(xdotool getwindowname "$id" 2>/dev/null || echo "Unknown")
                echo "  Window ID $id: $window_name" | tee -a "$DEBUG_LOG"
            done
            echo "$app_name is already running" | tee -a "$DEBUG_LOG"
        fi
        
        echo "----------------------------------------" | tee -a "$DEBUG_LOG"
    fi
done


if pgrep wispr_linux_rs > /dev/null; then
    echo "Wispr is already running" | tee -a "$DEBUG_LOG"
else
    echo "Wispr is not running, starting..." | tee -a "$DEBUG_LOG"
    '/home/tsuyoshi/ghq/github.com/nagamine-git/wispr_linux_rs/target/release/wispr_linux_rs' --config '/home/tsuyoshi/ghq/github.com/nagamine-git/wispr_linux_rs/config.toml' > "$LOG_DIR/wispr.log" 2>&1 &
fi


if pgrep toggl_linux_rs > /dev/null; then
    echo "Toggl is already running" | tee -a "$DEBUG_LOG"
else
    echo "Toggl is not running, starting..." | tee -a "$DEBUG_LOG"
    '/home/tsuyoshi/ghq/github.com/nagamine-git/toggl_linux_rs/target/release/toggl_linux_rs' --daemon --config '/home/tsuyoshi/ghq/github.com/nagamine-git/toggl_linux_rs/config.toml' > "$LOG_DIR/toggl.log" 2>&1 &
fi


if pgrep slack > /dev/null; then
    echo "Slack is already running" | tee -a "$DEBUG_LOG"
else
    echo "Slack is not running, starting..." | tee -a "$DEBUG_LOG"
    env BAMF_DESKTOP_FILE_HINT=/var/lib/snapd/desktop/applications/slack_slack.desktop /snap/bin/slack %U > "$LOG_DIR/slack.log" 2>&1 &
fi

echo "Script completed at $(date)" | tee -a "$DEBUG_LOG"
