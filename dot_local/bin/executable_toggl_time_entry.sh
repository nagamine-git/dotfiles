#!/bin/bash
# デバッグをセットアップ
set -e

# 設定値 - 環境変数または直接設定
TOGGL_EMAIL="${TOGGL_EMAIL:-your-email@example.com}"
TOGGL_PASSWORD="${TOGGL_PASSWORD:-your-password}"
TOGGL_WORKSPACE_ID="${TOGGL_WORKSPACE_ID:-your-workspace-id}"
POLL_INTERVAL="${POLL_INTERVAL:-30}"  # 秒単位
MIN_ACTIVITY_DURATION="${MIN_ACTIVITY_DURATION:-10}"  # 最小アクティビティ時間（秒）
TIMELINE_MODE="${TIMELINE_MODE:-false}"  # Timelineモード（短期間のエントリを作成）

# APIエンドポイント
TOGGL_API_BASE="https://api.track.toggl.com/api/v9"
CURRENT_ENTRY_URL="${TOGGL_API_BASE}/me/time_entries/current"
CREATE_ENTRY_URL="${TOGGL_API_BASE}/workspaces/${TOGGL_WORKSPACE_ID}/time_entries"

# ログファイル
LOG_FILE="$HOME/.local/share/toggl_time_entry.log"
STATE_FILE="$HOME/.local/share/toggl_current_window.state"
ACTIVITY_LOG="$HOME/.local/share/toggl_activity.log"

# ログ関数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# アクティビティログ関数
log_activity() {
    local window="$1"
    local start_time="$2"
    local end_time="$3"
    local duration="$4"
    echo "$(date '+%Y-%m-%d %H:%M:%S'),${window},${start_time},${end_time},${duration}" >> "$ACTIVITY_LOG"
}

# エラーハンドリング
error_exit() {
    log "ERROR: $1"
    exit 1
}

# 設定チェック
check_config() {
    if [[ "$TOGGL_EMAIL" == "your-email@example.com" ]] || [[ "$TOGGL_PASSWORD" == "your-password" ]] || [[ "$TOGGL_WORKSPACE_ID" == "your-workspace-id" ]]; then
        error_exit "設定を更新してください。環境変数 TOGGL_EMAIL, TOGGL_PASSWORD, TOGGL_WORKSPACE_ID を設定するか、スクリプト内の値を変更してください。"
    fi
    
    # ワークスペースIDが数値であることを確認
    if ! [[ "$TOGGL_WORKSPACE_ID" =~ ^[0-9]+$ ]]; then
        error_exit "TOGGL_WORKSPACE_ID は数値である必要があります。現在の値: $TOGGL_WORKSPACE_ID"
    fi
}

# Hyprlandのアクティブウィンドウ情報を取得
get_active_window() {
    local window_info
    if ! window_info=$(hyprctl activewindow -j 2>/dev/null); then
        echo "No active window"
        return 1
    fi
    
    local class=$(echo "$window_info" | jq -r '.class // "unknown"')
    local title=$(echo "$window_info" | jq -r '.title // "untitled"')
    local pid=$(echo "$window_info" | jq -r '.pid // 0')
    
    # 空のウィンドウは無視
    if [[ "$class" == "null" ]] || [[ "$class" == "" ]] || [[ "$title" == "null" ]] || [[ "$title" == "" ]]; then
        echo "No active window"
        return 1
    fi
    
    echo "${class}: ${title}"
}

# 現在実行中のTogglエントリを取得
get_current_entry() {
    curl -s -u "${TOGGL_EMAIL}:${TOGGL_PASSWORD}" \
         -H "Content-Type: application/json" \
         "$CURRENT_ENTRY_URL" 2>/dev/null || echo "null"
}

# 現在実行中のエントリを停止
stop_current_entry() {
    local current_entry="$1"
    local entry_id=$(echo "$current_entry" | jq -r '.id // empty')
    local workspace_id=$(echo "$current_entry" | jq -r '.workspace_id // empty')
    
    if [[ -n "$entry_id" ]] && [[ "$entry_id" != "null" ]] && [[ -n "$workspace_id" ]] && [[ "$workspace_id" != "null" ]]; then
        local stop_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        local update_url="${TOGGL_API_BASE}/workspaces/${workspace_id}/time_entries/${entry_id}"
        
        local response=$(curl -s -X PUT \
                            -u "${TOGGL_EMAIL}:${TOGGL_PASSWORD}" \
                            -H "Content-Type: application/json" \
                            -d "{\"stop\":\"${stop_time}\"}" \
                            "$update_url" 2>/dev/null)
        
        if [[ -n "$response" ]] && [[ "$response" != "null" ]]; then
            log "停止したエントリ: $(echo "$current_entry" | jq -r '.description // "No description"')"
            return 0
        else
            log "WARNING: エントリの停止に失敗しました (ID: $entry_id)"
            return 1
        fi
    fi
    return 1
}

# 完了したタイムエントリを作成（Timeline風）
create_completed_entry() {
    local description="$1"
    local start_time="$2"
    local duration="$3"
    
    # 最小時間チェック
    if [[ "$duration" -lt "$MIN_ACTIVITY_DURATION" ]]; then
        log "アクティビティが短すぎます ($duration秒): $description"
        return 1
    fi
    
    local json_data=$(jq -n \
                     --arg desc "$description" \
                     --arg start "$start_time" \
                     --argjson duration "$duration" \
                     --argjson workspace_id "$TOGGL_WORKSPACE_ID" \
                     --arg created_with "hyprland-timeline" \
                     --arg tags "activity" \
                     '{
                         description: $desc,
                         start: $start,
                         duration: $duration,
                         workspace_id: $workspace_id,
                         wid: $workspace_id,
                         created_with: $created_with,
                         tags: [$tags]
                     }')
    
    local response=$(curl -s -X POST \
                         -u "${TOGGL_EMAIL}:${TOGGL_PASSWORD}" \
                         -H "Content-Type: application/json" \
                         -d "$json_data" \
                         "$CREATE_ENTRY_URL" 2>/dev/null)
    
    if [[ -n "$response" ]] && [[ "$response" != "null" ]] && echo "$response" | jq -e '.id' >/dev/null 2>&1; then
        log "作成したアクティビティエントリ: $description (${duration}秒)"
        return 0
    else
        log "ERROR: アクティビティエントリの作成に失敗しました: $description"
        log "Response: $response"
        return 1
    fi
}

# 新しいタイムエントリを開始
start_new_entry() {
    local description="$1"
    
    if [[ "$TIMELINE_MODE" == "true" ]]; then
        # Timelineモードでは実行中エントリを作成しない
        return 0
    fi
    
    local start_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local start_unix=$(date +%s)
    local duration=$((start_unix * -1))
    
    local json_data=$(jq -n \
                     --arg desc "$description" \
                     --arg start "$start_time" \
                     --argjson duration "$duration" \
                     --argjson workspace_id "$TOGGL_WORKSPACE_ID" \
                     --arg created_with "hyprland-tracker" \
                     '{
                         description: $desc,
                         start: $start,
                         duration: $duration,
                         workspace_id: $workspace_id,
                         wid: $workspace_id,
                         created_with: $created_with
                     }')
    
    local response=$(curl -s -X POST \
                         -u "${TOGGL_EMAIL}:${TOGGL_PASSWORD}" \
                         -H "Content-Type: application/json" \
                         -d "$json_data" \
                         "$CREATE_ENTRY_URL" 2>/dev/null)
    
    if [[ -n "$response" ]] && [[ "$response" != "null" ]] && echo "$response" | jq -e '.id' >/dev/null 2>&1; then
        log "開始したエントリ: $description"
        return 0
    else
        log "ERROR: エントリの開始に失敗しました: $description"
        log "Response: $response"
        return 1
    fi
}

# アクティビティ統計表示
show_activity_stats() {
    if [[ ! -f "$ACTIVITY_LOG" ]]; then
        echo "アクティビティログが見つかりません"
        return 1
    fi
    
    echo "=== 今日のアクティビティ統計 ==="
    local today=$(date '+%Y-%m-%d')
    
    # 今日のアクティビティを抽出
    local today_activities=$(grep "^$today" "$ACTIVITY_LOG" 2>/dev/null || echo "")
    
    if [[ -z "$today_activities" ]]; then
        echo "今日のアクティビティはありません"
        return 0
    fi
    
    echo "$today_activities" | awk -F',' '
    BEGIN { 
        print "アプリケーション別時間:";
        total_time = 0;
    }
    {
        app = $2;
        duration = $5;
        total_time += duration;
        app_time[app] += duration;
    }
    END {
        for (app in app_time) {
            minutes = int(app_time[app] / 60);
            seconds = app_time[app] % 60;
            printf "  %s: %dm %ds\n", app, minutes, seconds;
        }
        total_minutes = int(total_time / 60);
        total_seconds = total_time % 60;
        printf "\n合計時間: %dm %ds\n", total_minutes, total_seconds;
    }'
}

# メイン処理
main() {
    log "Hyprland Toggl Time Tracker を開始しています..."
    
    if [[ "$TIMELINE_MODE" == "true" ]]; then
        log "Timelineモードが有効です"
    fi
    
    # 設定チェック
    check_config
    
    # 必要なコマンドの存在確認
    for cmd in hyprctl jq curl; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            error_exit "必要なコマンドが見つかりません: $cmd"
        fi
    done
    
    # 状態ファイルの初期化
    echo "" > "$STATE_FILE"
    
    # アクティビティログのヘッダー作成
    if [[ ! -f "$ACTIVITY_LOG" ]]; then
        echo "timestamp,window,start_time,end_time,duration" > "$ACTIVITY_LOG"
    fi
    
    local previous_window=""
    local activity_start_time=""
    
    while true; do
        local current_window
        if current_window=$(get_active_window); then
            # ウィンドウが変更された場合
            if [[ "$current_window" != "$previous_window" ]] && [[ -n "$current_window" ]]; then
                local current_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
                local current_unix=$(date +%s)
                
                # 前のアクティビティを記録
                if [[ -n "$previous_window" ]] && [[ -n "$activity_start_time" ]]; then
                    local duration=$((current_unix - activity_start_time))
                    log_activity "$previous_window" "$(date -u -d @$activity_start_time +"%Y-%m-%dT%H:%M:%SZ")" "$current_time" "$duration"
                    
                    if [[ "$TIMELINE_MODE" == "true" ]]; then
                        create_completed_entry "$previous_window" "$(date -u -d @$activity_start_time +"%Y-%m-%dT%H:%M:%SZ")" "$duration"
                    fi
                fi
                
                log "ウィンドウ変更検出: $current_window"
                
                if [[ "$TIMELINE_MODE" != "true" ]]; then
                    # 現在実行中のエントリを取得
                    local current_entry=$(get_current_entry)
                    
                    # 実行中のエントリがある場合は停止
                    if [[ "$current_entry" != "null" ]] && echo "$current_entry" | jq -e '.id' >/dev/null 2>&1; then
                        stop_current_entry "$current_entry"
                    fi
                    
                    # 新しいエントリを開始
                    start_new_entry "$current_window"
                fi
                
                echo "$current_window" > "$STATE_FILE"
                previous_window="$current_window"
                activity_start_time="$current_unix"
            fi
        else
            # アクティブウィンドウがない場合
            if [[ -n "$previous_window" ]]; then
                local current_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
                local current_unix=$(date +%s)
                
                # 最後のアクティビティを記録
                if [[ -n "$activity_start_time" ]]; then
                    local duration=$((current_unix - activity_start_time))
                    log_activity "$previous_window" "$(date -u -d @$activity_start_time +"%Y-%m-%dT%H:%M:%SZ")" "$current_time" "$duration"
                    
                    if [[ "$TIMELINE_MODE" == "true" ]]; then
                        create_completed_entry "$previous_window" "$(date -u -d @$activity_start_time +"%Y-%m-%dT%H:%M:%SZ")" "$duration"
                    fi
                fi
                
                log "アクティブウィンドウなし - エントリを停止"
                
                if [[ "$TIMELINE_MODE" != "true" ]]; then
                    local current_entry=$(get_current_entry)
                    if [[ "$current_entry" != "null" ]] && echo "$current_entry" | jq -e '.id' >/dev/null 2>&1; then
                        stop_current_entry "$current_entry"
                    fi
                fi
                
                previous_window=""
                activity_start_time=""
                echo "" > "$STATE_FILE"
            fi
        fi
        
        sleep "$POLL_INTERVAL"
    done
}

# シグナルハンドリング（Ctrl+Cで終了時に現在のエントリを停止）
cleanup() {
    log "終了シグナルを受信 - 現在のエントリを停止しています..."
    local current_entry=$(get_current_entry)
    if [[ "$current_entry" != "null" ]] && echo "$current_entry" | jq -e '.id' >/dev/null 2>&1; then
        stop_current_entry "$current_entry"
    fi
    log "Hyprland Toggl Time Tracker を終了しました"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ワークスペースID取得機能
get_workspace_ids() {
    echo "利用可能なワークスペースを取得中..."
    local workspaces=$(curl -s -u "${TOGGL_EMAIL}:${TOGGL_PASSWORD}" \
                           -H "Content-Type: application/json" \
                           "${TOGGL_API_BASE}/workspaces" 2>/dev/null)
    
    if [[ -n "$workspaces" ]] && [[ "$workspaces" != "null" ]]; then
        echo "利用可能なワークスペース:"
        echo "$workspaces" | jq -r '.[] | "ID: \(.id) - 名前: \(.name)"'
    else
        error_exit "ワークスペースの取得に失敗しました。認証情報を確認してください。"
    fi
}

# アクティビティ統計表示
if [[ "$1" == "--stats" ]]; then
    show_activity_stats
    exit 0
fi

# ヘルプ表示
if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    echo "Hyprland Toggl Time Tracker"
    echo ""
    echo "使用方法: $0 [オプション]"
    echo ""
    echo "環境変数:"
    echo "  TOGGL_EMAIL       - Togglのメールアドレス"
    echo "  TOGGL_PASSWORD    - Togglのパスワード"
    echo "  TOGGL_WORKSPACE_ID - TogglのワークスペースID（数値）"
    echo "  POLL_INTERVAL     - ポーリング間隔（秒、デフォルト: 30）"
    echo "  TIMELINE_MODE     - Timelineモード（true/false、デフォルト: false）"
    echo "  MIN_ACTIVITY_DURATION - 最小アクティビティ時間（秒、デフォルト: 10）"
    echo ""
    echo "オプション:"
    echo "  -h, --help        - このヘルプを表示"
    echo "  --check-config    - 現在の設定値を確認"
    echo "  --get-workspaces  - 利用可能なワークスペース一覧を表示"
    echo "  --stats           - 今日のアクティビティ統計を表示"
    echo ""
    echo "例:"
    echo "  # 通常モード（実行中エントリを作成）"
    echo "  TOGGL_EMAIL=user@example.com TOGGL_PASSWORD=pass TOGGL_WORKSPACE_ID=123456 $0"
    echo ""
    echo "  # Timelineモード（完了済みエントリのみ作成）"
    echo "  TIMELINE_MODE=true TOGGL_EMAIL=user@example.com TOGGL_PASSWORD=pass TOGGL_WORKSPACE_ID=123456 $0"
    echo ""
    echo "ワークスペースID取得:"
    echo "  TOGGL_EMAIL=user@example.com TOGGL_PASSWORD=pass $0 --get-workspaces"
    exit 0
fi

# ワークスペース取得オプション
if [[ "$1" == "--get-workspaces" ]]; then
    if [[ "$TOGGL_EMAIL" == "your-email@example.com" ]] || [[ "$TOGGL_PASSWORD" == "your-password" ]]; then
        error_exit "TOGGL_EMAIL と TOGGL_PASSWORD を設定してください。"
    fi
    get_workspace_ids
    exit 0
fi

# メイン処理実行
main

