#!/usr/bin/env bash
# Toggl status for Waybar (JST + text output)
# Shows "<description> <MM:SS>" as text.
# Tooltip contains description and start time in JST.
# Requirements: curl jq
set -euo pipefail

API_TOKEN="${TOGGL_API_TOKEN:-}"
TOKEN_FILE="${TOGGL_TOKEN_FILE:-$HOME/.config/waybar/toggl_token}"
if [[ -z "$API_TOKEN" && -f "$TOKEN_FILE" ]]; then
  API_TOKEN="$(<"$TOKEN_FILE")"
fi
if [[ -z "$API_TOKEN" ]]; then
  printf '{"text":"⚠️⚠️⚠️TOGGL IDLE⚠️⚠️⚠️","tooltip":"Token not set"}\n'
  exit 0
fi

API_URL="https://api.track.toggl.com/api/v9/me/time_entries/current"
response=$(curl -s -u "$API_TOKEN:api_token" "$API_URL" 2>/dev/null || true)
if [[ -z "$response" || "$response" == "null" ]]; then
  printf '{"text":"⚠️⚠️⚠️TOGGL IDLE⚠️⚠️⚠️","tooltip":"No running entry"}\n'
  exit 0
fi

description=$(echo "$response" | jq -r '.description // "No description"')
start_utc=$(echo "$response" | jq -r '.start')
# epoch seconds
start_epoch=$(date -d "$start_utc" +%s)
now_epoch=$(date +%s)

elapsed=$((now_epoch - start_epoch))
hours=$((elapsed/3600))
minutes=$(((elapsed%3600)/60))
if [[ $hours -gt 0 ]]; then
  printf -v elapsed_str "0%d:%02d" "$hours" "$minutes"
else
  printf -v elapsed_str "00:%02d" "$minutes"
fi

# Convert start time to JST for tooltip
start_jst=$(TZ="Asia/Tokyo" date -d "$start_utc" '+%Y-%m-%d %H:%M:%S')

# Truncate description if too long for bar (optional 30 chars)
maxlen=30
if (( ${#description} > maxlen )); then
  description="${description:0:maxlen}…"
fi

text="${description} ${elapsed_str}"
printf '{"text":"%s","tooltip":"%s (開始: %s JST)"}\n' "$text" "$description" "$start_jst"
