#!/usr/bin/env bash

# Sleep wake backup script
# Executes backup after system wakes from sleep when CPU usage is low

set -eu

# Configuration
CPU_THRESHOLD=20  # CPU usage threshold (percentage)
WAIT_TIME=300     # Wait time after wake (seconds)
CHECK_INTERVAL=30 # Check interval (seconds)
MAX_WAIT=1800     # Maximum wait time (30 minutes)

# Logging
LOG_FILE="/tmp/sleep-backup.log"
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Check if system is waking from sleep
is_waking_from_sleep() {
    # Check if system was recently suspended
    local suspend_time=$(journalctl --since "5 minutes ago" | grep -E "suspend|sleep" | tail -1 | awk '{print $3}' || echo "")
    if [ -n "$suspend_time" ]; then
        return 0
    fi
    return 1
}

# Get current CPU usage
get_cpu_usage() {
    # Get CPU usage from /proc/stat
    local cpu_info=$(grep '^cpu ' /proc/stat)
    local idle=$(echo $cpu_info | awk '{print $5}')
    local total=0
    for val in $cpu_info; do
        total=$((total + val))
    done
    local usage=$((100 - (idle * 100) / total))
    echo $usage
}

# Check if CPU usage is low
is_cpu_low() {
    local cpu_usage=$(get_cpu_usage)
    if [ "$cpu_usage" -lt "$CPU_THRESHOLD" ]; then
        return 0
    fi
    return 1
}

# Execute backup
execute_backup() {
    log "Starting backup after sleep wake..."
    
    # Check if timeshift is available
    if ! command -v timeshift >/dev/null 2>&1; then
        log "Timeshift not found, skipping backup"
        return 1
    fi
    
    # Execute backup
    if sudo timeshift --create --comments "Sleep wake backup $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE" 2>&1; then
        log "Backup completed successfully"
        return 0
    else
        log "Backup failed"
        return 1
    fi
}

# Main function
main() {
    log "Sleep backup script started"
    
    # Check if system is waking from sleep
    if ! is_waking_from_sleep; then
        log "System not waking from sleep, exiting"
        exit 0
    fi
    
    log "System detected waking from sleep, waiting for CPU to stabilize..."
    
    # Wait for system to stabilize
    local waited=0
    while [ $waited -lt $MAX_WAIT ]; do
        if is_cpu_low; then
            log "CPU usage is low ($(get_cpu_usage)%), executing backup"
            execute_backup
            exit 0
        fi
        
        log "CPU usage is high ($(get_cpu_usage)%), waiting..."
        sleep $CHECK_INTERVAL
        waited=$((waited + CHECK_INTERVAL))
    done
    
    log "Maximum wait time reached, executing backup anyway"
    execute_backup
}

# Run main function
main "$@"



