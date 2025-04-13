#!/bin/bash
set -e

# ログディレクトリの作成
LOG_DIR="$HOME/.local/log"
mkdir -p "$LOG_DIR"

# デスクトップエントリを実行
for file in ~/Desktop/startup/*.desktop; do
    if [ -f "$file" ]; then
        gio launch "$file" &
    fi
done

# Wisprの実行とログ取得
'/home/tsuyoshi/ghq/github.com/nagamine-git/wispr_linux_rs/target/release/wispr_linux_rs' --config '/home/tsuyoshi/ghq/github.com/nagamine-git/wispr_linux_rs/config.toml' > "$LOG_DIR/wispr.log" 2>&1 &
echo "Wispr started. View logs with: tail -f $LOG_DIR/wispr.log"

# Togglの実行とログ取得
'/home/tsuyoshi/ghq/github.com/nagamine-git/toggl_linux_rs/target/release/toggl_linux_rs' --daemon --config '/home/tsuyoshi/ghq/github.com/nagamine-git/toggl_linux_rs/config.toml' > "$LOG_DIR/toggl.log" 2>&1 &
echo "Toggl started. View logs with: tail -f $LOG_DIR/toggl.log"
