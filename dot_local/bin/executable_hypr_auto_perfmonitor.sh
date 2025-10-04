#!/usr/bin/env bash
# ~/bin/hypr_auto_perfmonitor.sh
# 実用的な自動パフォーマンス監視・調整システム
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=dot_local/bin/lib_hypr_perfmode.sh
source "$SCRIPT_DIR/lib_hypr_perfmode.sh"

# CPU使用率計算用の前回値
PREV_TOTAL=0
PREV_IDLE=0
HAVE_BASELINE=false

# === 設定 ===
readonly STATE_FILE=/tmp/hypr_perf_mode
readonly LOCK_FILE=/tmp/hypr_perfmonitor.lock
readonly STATUS_FILE=/tmp/hypr_perfmonitor_status
readonly MONITOR_INTERVAL=5           # 監視間隔（秒）- より頻繁にチェック
readonly LOG_FILE="$HOME/.local/share/hypr_perfmonitor.log"
readonly LOG_DIR="$(dirname "$LOG_FILE")"
readonly NOTIFICATION_COOLDOWN=120    # 通知のクールダウン時間（秒）

# しきい値設定（実用的）
readonly CPU_HIGH_THRESHOLD=60.0     # CPU使用率60%超で高負荷
readonly CPU_LOW_THRESHOLD=30.0      # CPU使用率30%未満で低負荷
readonly TEMP_THRESHOLD=70           # 70°C超で強制パフォーマンス

# === ロック管理 ===
cleanup() {
    if [[ -f "$LOCK_FILE" ]] && [[ "$(cat "$LOCK_FILE" 2>/dev/null)" == "$$" ]]; then
        rm -f "$LOCK_FILE"
    fi
}

setup_lock_trap() {
    trap 'cleanup' EXIT
    trap 'cleanup; exit 0' INT TERM
}

get_monitor_pid() {
    if [[ -f "$LOCK_FILE" ]]; then
        local pid
        pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        rm -f "$LOCK_FILE"
    fi
    return 1
}

acquire_lock() {
    local existing_pid
    if existing_pid=$(get_monitor_pid); then
        echo "Monitor already running (PID: ${existing_pid})"
        return 1
    fi

    echo $$ > "$LOCK_FILE"
    setup_lock_trap
    return 0
}

# === ログ関数 ===
log() {
    if ! mkdir -p "$LOG_DIR" 2>/dev/null; then
        return
    fi

    if [[ -w "$LOG_FILE" ]]; then
        printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_FILE"
        return
    fi

    if [[ ! -e "$LOG_FILE" ]] && touch "$LOG_FILE" 2>/dev/null; then
        printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_FILE"
    fi
}

# === 現在のモード取得 ===
get_current_mode() {
    [[ -f "$STATE_FILE" ]] && echo "performance" || echo "normal"
}

# === CPU使用率取得（より正確） ===
get_cpu_usage() {
    local _cpu user nice system idle iowait irq softirq steal guest guest_nice
    read -r _cpu user nice system idle iowait irq softirq steal guest guest_nice < /proc/stat

    local idle_all=$((idle + iowait))
    local non_idle=$((user + nice + system + irq + softirq + steal))
    local total=$((idle_all + non_idle))

    if [[ "$HAVE_BASELINE" == false ]]; then
        PREV_TOTAL=$total
        PREV_IDLE=$idle_all
        HAVE_BASELINE=true

        # Take a second sample immediately so one-shot status calls get a real value
        sleep 0.25
        read -r _cpu user nice system idle iowait irq softirq steal guest guest_nice < /proc/stat

        idle_all=$((idle + iowait))
        non_idle=$((user + nice + system + irq + softirq + steal))
        total=$((idle_all + non_idle))

        local totald_first=$((total - PREV_TOTAL))
        local idled_first=$((idle_all - PREV_IDLE))
        PREV_TOTAL=$total
        PREV_IDLE=$idle_all

        if (( totald_first <= 0 )); then
            echo "0"
            return
        fi

        awk -v totald="$totald_first" -v idled="$idled_first" 'BEGIN { printf "%.1f", (totald - idled) * 100 / totald }'
        return
    fi

    local totald=$((total - PREV_TOTAL))
    local idled=$((idle_all - PREV_IDLE))
    PREV_TOTAL=$total
    PREV_IDLE=$idle_all

    if (( totald <= 0 )); then
        echo "0"
        return
    fi

    awk -v totald="$totald" -v idled="$idled" 'BEGIN { printf "%.1f", (totald - idled) * 100 / totald }'
}

# === CPU温度取得（複数ソース対応） ===
get_cpu_temp() {
    local temp=0
    
    # AMD Ryzen系 (k10temp)
    if [[ -f /sys/class/hwmon/hwmon1/temp1_input ]]; then
        temp=$(cat /sys/class/hwmon/hwmon1/temp1_input 2>/dev/null || echo 0)
        temp=$((temp / 1000))
    # Intel系
    elif [[ -f /sys/class/thermal/thermal_zone0/temp ]]; then
        temp=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0)
        temp=$((temp / 1000))
    # ThinkPad系
    elif [[ -f /sys/devices/platform/thinkpad_hwmon/hwmon/hwmon6/temp1_input ]]; then
        temp=$(cat /sys/devices/platform/thinkpad_hwmon/hwmon/hwmon6/temp1_input 2>/dev/null || echo 0)
        temp=$((temp / 1000))
    # sensors コマンド使用
    else
        temp=$(sensors 2>/dev/null | grep -i 'temp1' | head -1 | awk '{print $2}' | sed 's/+//;s/°C//' | cut -d. -f1 2>/dev/null || echo 0)
    fi
    
    echo "$temp"
}

# === waybar用ステータス更新 ===
update_status_file() {
    local mode="$1"
    local cpu_usage="$2"
    local cpu_temp="$3"
    
    # モード表示用のアイコン
    local mode_icon
    if [[ "$mode" == "performance" ]]; then
        mode_icon="🚀"
    else
        mode_icon="🌈"
    fi
    
    # waybar用のJSON形式でステータスを出力
    cat > "$STATUS_FILE" << EOF
{
    "text": "${mode_icon} ${cpu_usage}%",
    "tooltip": "Performance Mode: ${mode}\\nCPU Usage: ${cpu_usage}% (threshold: H:${CPU_HIGH_THRESHOLD}%, L:${CPU_LOW_THRESHOLD}%)\\nCPU Temp: ${cpu_temp}°C (threshold: ${TEMP_THRESHOLD}°C)",
    "class": "${mode}",
    "percentage": ${cpu_usage%.*}
}
EOF
}

# === パフォーマンスモード切り替え ===
switch_to_performance() {
    local cpu_usage="${1:-}"
    local cpu_temp="${2:-}"

    if [[ -z "$cpu_usage" ]]; then
        cpu_usage=$(get_cpu_usage)
    fi
    if [[ -z "$cpu_temp" ]]; then
        cpu_temp=$(get_cpu_temp)
    fi

    local current_mode
    current_mode=$(get_current_mode)
    [[ "$current_mode" == "performance" ]] && return 0
    
    log "Switching to PERFORMANCE mode (CPU: ${cpu_usage}%, Temp: ${cpu_temp}°C)"
    
    # Hyprland設定変更
    if ! hyprctl --batch "$HYPR_PERFORMANCE_BATCH" >/dev/null 2>&1; then
        log "hyprctl performance batch failed"
    fi

    # CPUガバナー変更
    if command -v cpupower >/dev/null 2>&1; then
        sudo cpupower frequency-set -g performance >/dev/null 2>&1 || true
    fi

    touch "$STATE_FILE"
    update_status_file "performance" "$cpu_usage" "$cpu_temp"
    
    # 通知のクールダウンチェック
    local last_notification_file=/tmp/hypr_perf_last_notification
    local current_time
    current_time=$(date +%s)
    
    if [[ ! -f "$last_notification_file" ]] || \
       [[ $((current_time - $(cat "$last_notification_file" 2>/dev/null || echo 0))) -gt $NOTIFICATION_COOLDOWN ]]; then
        notify-send "System Monitor" "🚀 パフォーマンスモード ON (CPU: ${cpu_usage}%)" -u low
        echo "$current_time" > "$last_notification_file"
    fi
}

switch_to_normal() {
    local cpu_usage="${1:-}"
    local cpu_temp="${2:-}"

    if [[ -z "$cpu_usage" ]]; then
        cpu_usage=$(get_cpu_usage)
    fi
    if [[ -z "$cpu_temp" ]]; then
        cpu_temp=$(get_cpu_temp)
    fi

    local current_mode
    current_mode=$(get_current_mode)
    [[ "$current_mode" == "normal" ]] && return 0
    
    log "Switching to NORMAL mode (CPU: ${cpu_usage}%, Temp: ${cpu_temp}°C)"
    
    # Hyprland設定変更
    if ! hyprctl --batch "$HYPR_NORMAL_BATCH" >/dev/null 2>&1; then
        log "hyprctl normal batch failed"
    fi

    # CPUガバナー変更
    if command -v cpupower >/dev/null 2>&1; then
        sudo cpupower frequency-set -g schedutil >/dev/null 2>&1 || true
    fi

    rm -f "$STATE_FILE"
    update_status_file "normal" "$cpu_usage" "$cpu_temp"
    
    # 通知のクールダウンチェック
    local last_notification_file=/tmp/hypr_perf_last_notification
    local current_time
    current_time=$(date +%s)
    
    if [[ ! -f "$last_notification_file" ]] || \
       [[ $((current_time - $(cat "$last_notification_file" 2>/dev/null || echo 0))) -gt $NOTIFICATION_COOLDOWN ]]; then
        notify-send "System Monitor" "🌈 通常モード (CPU: ${cpu_usage}%)" -u low
        echo "$current_time" > "$last_notification_file"
    fi
}

# === メイン監視ループ ===
main_monitor_loop() {
    log "Starting performance monitor (PID: $$)"
    
    local consecutive_high=0
    local consecutive_normal=0
    
    while true; do
        local cpu_usage cpu_temp current_mode
        cpu_usage=$(get_cpu_usage)
        cpu_temp=$(get_cpu_temp)
        current_mode=$(get_current_mode)
        
        # 現在のステータスをwaybar用ファイルに更新（毎回更新）
        update_status_file "$current_mode" "$cpu_usage" "$cpu_temp"
        
        # 判定ロジック（シンプル化）
        local should_be_performance=false
        
        # CPU温度が高い場合は必ずパフォーマンスモード
        if [[ $cpu_temp -gt $TEMP_THRESHOLD ]]; then
            should_be_performance=true
            log "High CPU temp detected: ${cpu_temp}°C"
        # CPU使用率が高い場合
        elif (( $(echo "$cpu_usage > $CPU_HIGH_THRESHOLD" | bc -l 2>/dev/null || echo "0") )); then
            should_be_performance=true
        # CPU使用率が低い場合は通常モード
        elif (( $(echo "$cpu_usage < $CPU_LOW_THRESHOLD" | bc -l 2>/dev/null || echo "0") )); then
            should_be_performance=false
        fi
        
        # モード切り替えの判定（ヒステリシス）
        if [[ "$current_mode" == "normal" ]] && [[ "$should_be_performance" == "true" ]]; then
            ((consecutive_high += 1))
            consecutive_normal=0
            
            # 2回連続で高負荷を検出したら切り替え
            if [[ $consecutive_high -ge 2 ]]; then
                switch_to_performance "$cpu_usage" "$cpu_temp"
                consecutive_high=0
            fi
            
        elif [[ "$current_mode" == "performance" ]] && [[ "$should_be_performance" == "false" ]]; then
            ((consecutive_normal += 1))
            consecutive_high=0
            
            # 3回連続で低負荷を検出したら切り替え
            if [[ $consecutive_normal -ge 3 ]]; then
                switch_to_normal "$cpu_usage" "$cpu_temp"
                consecutive_normal=0
            fi
        else
            consecutive_high=0
            consecutive_normal=0
        fi
        
        # デバッグ用ログ出力（1分毎）
        if [[ $(($(date +%s) % 60)) -lt $MONITOR_INTERVAL ]]; then
            log "Status: mode=$current_mode, CPU=${cpu_usage}%, temp=${cpu_temp}°C, consec_high=$consecutive_high, consec_normal=$consecutive_normal"
        fi
        
        sleep "$MONITOR_INTERVAL"
    done
}

# === 使用法表示 ===
usage() {
    cat << EOF
Usage: $0 [OPTION]
Options:
  start     Start monitoring daemon
  stop      Stop monitoring daemon
  status    Show current status
  log       Show recent log entries
  test      Test sensors and thresholds
  
Manual control:
  perf      Force performance mode
  normal    Force normal mode
EOF
}

# === メイン処理 ===
case "${1:-start}" in
    start)
        if [[ -t 1 ]]; then
            if monitor_pid=$(get_monitor_pid); then
                echo "Performance monitor already running (PID: ${monitor_pid})"
                exit 0
            fi
            nohup "$0" daemon >/dev/null 2>&1 &
            echo "Performance monitor started (PID: $!)"
        else
            acquire_lock || exit 0
            main_monitor_loop
        fi
        ;;
    daemon)
        acquire_lock || exit 0
        main_monitor_loop
        ;;
    stop)
        if monitor_pid=$(get_monitor_pid); then
            if kill "$monitor_pid" 2>/dev/null; then
                sleep 0.2
            fi
            if kill -0 "$monitor_pid" 2>/dev/null; then
                sleep 1
            fi
            if kill -0 "$monitor_pid" 2>/dev/null; then
                echo "Failed to stop monitor (PID: ${monitor_pid})"
                exit 1
            fi
            rm -f "$LOCK_FILE"
            echo "Performance monitor stopped"
        else
            echo "No monitor running"
        fi
        ;;
    status)
        current_mode=$(get_current_mode)
        cpu_usage=$(get_cpu_usage)
        cpu_temp=$(get_cpu_temp)
        
        update_status_file "$current_mode" "$cpu_usage" "$cpu_temp"
        
        echo "🔧 Performance Monitor Status"
        echo "Mode: $current_mode"
        echo "CPU Usage: ${cpu_usage}% (threshold: H:${CPU_HIGH_THRESHOLD}%, L:${CPU_LOW_THRESHOLD}%)"
        echo "CPU Temp: ${cpu_temp}°C (threshold: ${TEMP_THRESHOLD}°C)"
        if monitor_pid=$(get_monitor_pid); then
            echo "Running: Yes (PID: ${monitor_pid})"
        else
            echo "Running: No"
        fi
        echo "Status file: $STATUS_FILE"
        ;;
    test)
        echo "🧪 Testing sensors and detection..."
        echo "CPU Usage: $(get_cpu_usage)%"
        echo "CPU Temp: $(get_cpu_temp)°C"
        echo "Load Average: $(cat /proc/loadavg | cut -d' ' -f1)"
        echo "Top CPU: $(top -bn1 | grep "Cpu(s)")"
        echo "Sensors:"
        sensors 2>/dev/null | grep -i temp || echo "No sensors found"
        ;;
    log)
        tail -n 20 "$LOG_FILE" 2>/dev/null || echo "No log file found"
        ;;
    perf)
        switch_to_performance
        ;;
    normal)
        switch_to_normal
        ;;
    *)
        usage
        exit 1
        ;;
esac
