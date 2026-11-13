#!/usr/bin/env bash
# Simple GPU status for Waybar (utilization + temp when available)
# - NVIDIA: uses nvidia-smi
# - AMD (amdgpu): reads /sys gpu_busy_percent and hwmon temp
# - Others: no output (module stays hidden)
set -euo pipefail

braille_step() {
  # Map 0-100 to 8-step braille-like ramp used elsewhere
  local p=$1
  (( p < 0 )) && p=0
  (( p > 100 )) && p=100
  local -a icons=("⡀" "⣀" "⣄" "⣤" "⣦" "⣶" "⣷" "⣿")
  local idx=$(( p * 8 / 101 ))
  (( idx < 0 )) && idx=0
  (( idx > 7 )) && idx=7
  printf '%s' "${icons[$idx]}"
}

json_escape() {
  # Escape a string for safe inclusion in JSON (handles \ " and newlines)
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

print_json() {
  local util=$1 temp=$2
  local icon
  icon=$(braille_step "$util")

  # Choose class by threshold similar to CPU
  local class="normal"
  if (( util >= 95 )); then
    class="critical"
  elif (( util >= 80 )); then
    class="warning"
  fi

  local text="󰢮 ${icon}"   # GPU-ish icon + ramp
  local tooltip
  if [[ -n "$temp" ]]; then
    # Keep tooltip one line in JSON by escaping newline
    tooltip=$(printf 'GPU: %d%%\nTemp: %s°C' "$util" "$temp")
  else
    tooltip=$(printf 'GPU: %d%%' "$util")
  fi

  printf '{"text":"%s","class":"%s","tooltip":"%s"}\n' "$(json_escape "$text")" "$class" "$(json_escape "$tooltip")"
}

# Try NVIDIA first
if command -v nvidia-smi >/dev/null 2>&1; then
  # Query utilization (%) and temperature (C) of GPU 0
if out=$(nvidia-smi --query-gpu=utilization.gpu,temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -n1); then
    # e.g. "12, 45" → util=12 temp=45
    out=${out// /}
    util=${out%%,*}
    temp=${out##*,}
    if [[ "$util" =~ ^[0-9]+$ ]]; then
      print_json "$util" "$temp"
      exit 0
    fi
  fi
fi

# Try AMD (amdgpu): gpu_busy_percent and hwmon temp
busy_file=""
for f in /sys/class/drm/card*/device/gpu_busy_percent; do
  [[ -r "$f" ]] && busy_file="$f" && break
done

if [[ -n "$busy_file" ]]; then
  util=$(<"$busy_file")
  # Find a temperature file if available
  temp=""
  shopt -s nullglob
  for t in /sys/class/drm/card*/device/hwmon/hwmon*/temp1_input; do
    if [[ -r "$t" ]]; then
      val=$(<"$t")
      # Convert millideg to deg C if needed
      if [[ "$val" =~ ^[0-9]+$ ]]; then
        if (( val > 1000 )); then
          temp=$(( val / 1000 ))
        else
          temp=$val
        fi
        break
      fi
    fi
  done
  shopt -u nullglob

  if [[ "$util" =~ ^[0-9]+$ ]]; then
    print_json "$util" "${temp:-}"
    exit 0
  fi
fi

# Not supported: produce no output so the module hides
exit 0
