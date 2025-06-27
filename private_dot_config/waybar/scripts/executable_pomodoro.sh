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
hour=$((10#$hour)) 
sec=$(date +%S)                              # seconds value for optional blinking animation
sec=$((10#$sec))

# ---- build bar -------------------------------------------------------------
work_seg_total=5  # segments for 50-min work

if (( min < 50 )); then  # -------------------- Work phase ------------
  # 1) Break segment (still ahead)
  text="$fill"
  segments=1

  # 2) Work remaining segments (5 slots)
  remaining=$((50 - min))              # 50 → 1
  full=$(( remaining / 10 ))           # 0-5 complete 10-min blocks
  rem=$(( remaining % 10 ))

  #   a) full 10-min blocks
  for ((i=0;i<full;i++)); do text+="$fill"; segments=$((segments+1)); done
  #   b) partial block for current 10-min chunk
  if (( rem > 0 )); then
    idx=$(( (10 - rem) * 8 / 10 ))     # 1-9 → fade index 0-7
    text+="${partials[$idx]}"
    segments=$((segments+1))
  fi
  #   c) pad rest with empty blocks
  while (( segments < (1+work_seg_total) )); do text+="$empty_markup"; segments=$((segments+1)); done

  class="work"
  (( remaining <= 10 )) && class="warning"

else                         # ------------- Break phase --------------
  # 1) Break segment (counts down)
  passed=$(( min - 50 ))     # 0-9 elapsed in break
  remaining_break=$(( 10 - passed ))
  if (( remaining_break == 10 )); then
    text="$fill"
    segments=1
  else
    idx=$(( (10 - remaining_break) * 8 / 10 )) # same fade logic
    text="${partials[$idx]}"
    segments=1
  fi

  # 2) All work segments greyed out
  for ((i=segments;i<1+work_seg_total;i++)); do text+="$empty_markup"; done

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
