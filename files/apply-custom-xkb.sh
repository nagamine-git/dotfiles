#!/bin/bash

LOG_FILE="$HOME/.xkb_setup.log"
echo "start XKB setup: $(date)" > $LOG_FILE

setxkbmap -option
echo "clear existing settings" >> $LOG_FILE

setxkbmap -layout us -variant colemak -option
echo "apply colemak layout" >> $LOG_FILE

setxkbmap -I/usr/share/X11/xkb -layout custom -variant vim
RESULT=$?
if [ $RESULT -eq 0 ]; then
    echo "apply custom XKB layout" >> $LOG_FILE
else
    echo "apply custom XKB layout failed: exit code $RESULT" >> $LOG_FILE
    # 失敗した場合の代替手段
    echo "apply alternative settings" >> $LOG_FILE
    setxkbmap -option ctrl:nocaps
    echo "set CapsLock to Ctrl" >> $LOG_FILE
fi

xkbcomp -xkb $DISPLAY - | grep -i custom >> $LOG_FILE 2>&1
echo "current XKB settings:" >> $LOG_FILE
setxkbmap -print -verbose 10 >> $LOG_FILE 2>&1

echo "XKB setup completed: $(date)" >> $LOG_FILE 