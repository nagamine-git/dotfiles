#!/bin/bash

set -eu

LOG_FILE="$HOME/.xkb_setup.log"
echo "start XKB setup: $(date)" > $LOG_FILE

setxkbmap -option
echo "clear existing settings" >> $LOG_FILE

setxkbmap -layout us -variant colemak -option
echo "apply colemak layou 1" >> $LOG_FILE

echo "trying to apply custom XKB layout..." >> $LOG_FILE
setxkbmap -I$HOME/.local/share/xkb/symbols/custom -layout custom -variant vim
RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo "custom XKB layout applied successfully" >> $LOG_FILE
else
    echo "custom XKB layout failed: exit code $RESULT" >> $LOG_FILE
    # 失敗した場合
    echo "apply alternative settings" >> $LOG_FILE
    setxkbmap -option ctrl:nocaps
    echo "set CapsLock to Ctrl" >> $LOG_FILE
fi

echo "current keyboard settings:" >> $LOG_FILE
xkbcomp -xkb $DISPLAY - | grep -i custom >> $LOG_FILE 2>&1
setxkbmap -print -verbose 10 >> $LOG_FILE 2>&1

echo "XKB setup completed: $(date)" >> $LOG_FILE
