#!/usr/bin/env bash
# 50 min work / 10 min break pomodoro for Waybar
# icon sets
fill="⣿"                                    # full bar
partials=(⣿ ⣷ ⣶ ⣦ ⣤ ⣄ ⣀ ⡀)             # 8-step fade from full→empty

min=$(date +%M)
min=$((10#$min))                              # strip leading zero
hour=$(date +%H)

if (( min < 50 )); then                      # Work phase
  remaining=$((50 - min))
  full=$(( remaining / 10 ))                 # 0-5 full bars
  rem=$(( remaining % 10 ))
  text=""
  for ((i=0; i<full; i++)); do               # build string safely for multibyte char
    text+="$fill"
  done
  if (( rem > 0 )); then                     # partial bar for current 10-min block
    idx=$(( (10 - rem) * 8 / 10 ))           # map 1-9→0-7
    text+="${partials[$idx]}"
  fi
  class="work"
  (( remaining <= 10 )) && class="warning"   # last 10 min red
else                                          # Break phase (10 min)
  passed=$(( min - 50 ))                     # 0-9
  idx=$(( passed * 8 / 10 ))                 # 0-7
  text="${partials[$idx]}"
  class="break"
fi

printf '{"text":"%s","class":"%s","tooltip":"%s %02d:%02d"}\n' \
       "$text" "$class" "$class" "$hour" "$min"
