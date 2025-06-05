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
for file in ~/.local/share/applications/brave-*-Default.desktop; do
    if [ -f "$file" ]; then
        # Extract Name from desktop file
        app_name=$(grep -oP '^Name=\K.*' "$file")
        echo "Found desktop file: $file with app_name: $app_name" | tee -a "$DEBUG_LOG"
        
        # Extract base name (remove notification count patterns like (9+))
        base_name=$(echo "$app_name" | sed 's/ *([0-9]\+[+]*)//')
        echo "Base name for search: $base_name" | tee -a "$DEBUG_LOG"
        
        # Check if window with this name already exists
        window_ids=$(xdotool search --name ".*${base_name}.*" 2>/dev/null || echo "")
        
        # デスクトップファイル名からPWA IDを抽出
        pwa_id=$(basename "$file" .desktop | sed -n 's/.*-\([a-z0-9]\{32\}\)-.*/\1/p')

        if [ -n "$pwa_id" ]; then
            echo "Checking for running PWA with ID: $pwa_id" | tee -a "$DEBUG_LOG"
            
            # そのIDを含むプロセスが既に起動しているかチェック
            if ps aux | grep -v grep | grep -q "$pwa_id"; then
                echo "$app_name is already running (PWA ID: $pwa_id). Skipping..." | tee -a "$DEBUG_LOG"
                continue  # または return、スクリプトの構造による
            fi
        fi

        if [ -z "$window_ids" ]; then
            echo "Starting $app_name..." | tee -a "$DEBUG_LOG"
            gtk-launch "$(basename "$file" .desktop)" > "$LOG_DIR/${app_name// /_}.log" 2>&1 &
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

if pgrep slack > /dev/null; then
    echo "Slack is already running" | tee -a "$DEBUG_LOG"
else
    echo "Slack is not running, starting..." | tee -a "$DEBUG_LOG"
    /usr/bin/slack --disable-gpu-compositing --enable-features=UseOzonePlatform --ozone-platform=wayland --enable-wayland-ime --enable-features=WebRTCPipeWireCapturer --enable-features=WaylandWindowDecorations --disable-features=WaylandFractionalScaleV1 -s 2>/dev/null &
    disown
fi

echo "Script completed at $(date)" | tee -a "$DEBUG_LOG"
