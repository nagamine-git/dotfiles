#!/usr/bin/env bash
# 50 min work / 10 min break pomodoro for Waybar
# icon sets
fill="⣿"                                    # full bar
partials=(⣿ ⣷ ⣶ ⣦ ⣤ ⣄ ⣀ ⡀)
empty="⣿"               # base char for empty segment
empty_markup="<span foreground='#aaaaaa20'>⣿</span>"  # light grey full block
total_seg=6             # 8-step fade from full→empty

min=$(date +%M)
min=$((10#$min))                              # strip leading zero
hour=$(date +%H)
sec=$(date +%S)                              # seconds value for optional blinking animation
sec=$((10#$sec))

if (( min < 50 )); then                      # Work phase
  remaining=$((50 - min))
  full=$(( remaining / 10 ))                 # 0-5 full bars
  rem=$(( remaining % 10 ))
  text=""
segments=0
  for ((i=0; i<full; i++)); do               # build string safely for multibyte char
    text+="$fill"
  done
segments=$full
  if (( rem > 0 )); then                     # partial bar for current 10-min block
    idx=$(( (10 - rem) * 8 / 10 ))           # map 1-9→0-7
    text+="${partials[$idx]}"
segments=$((segments+1))
  fi
  # pad with empties to reach total_seg
while (( segments < total_seg )); do text+="$empty_markup"; segments=$((segments+1)); done

class="work"
  (( remaining <= 10 )) && class="warning"   # last 10 min red
else                                          # Break phase (10 min)
  passed=$(( min - 50 ))                     # 0-9
  idx=$(( passed * 8 / 10 ))                 # 0-7
  text="${partials[$idx]}"
segments=1
while (( segments < total_seg )); do text+="$empty_markup"; segments=$((segments+1)); done
  class="break"
fi

# ---- blink handling -------------------------------------------------------
# During the last minute of each phase (min 49 just before break, min 59 just before work)
# add a CSS class "blink" every other second to flash the bar.  Define the
# animation in Waybar's CSS:
# adding an extra CSS class "blink" on even-numbered seconds.  Define the
# animation in Waybar's CSS:
# .blink { animation: blink 1s steps(2,start) infinite; }
# @keyframes blink { to { visibility: hidden; } }
classes="$class"
if (( min == 49 || min == 59 )); then
  (( sec % 2 == 0 )) && classes+=" blink"
fi

# ---- optional desktop notifications --------------------------------------
# Send a single notification exactly at 50:00 (start break) and 00:00 (back to work)
# Requires `notify-send` (libnotify).  Waybar typically executes this script every
# second, so we gate on sec==0 to avoid duplicates.
if (( (min == 50 || min == 0) && sec == 0 )); then
  if (( min == 50 )); then
    notify-send -u normal -i alarm-symbolic "Pomodoro" "Break time! 10 min rest"
  else
    notify-send -u normal -i alarm-symbolic "Pomodoro" "Back to work! 50 min focus"
  fi
fi

printf '{"text":"%s","class":"%s","tooltip":"%s %02d:%02d"}\n' \
       "$text" "$classes" "$class" "$hour" "$min"
