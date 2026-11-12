#!/bin/sh
# darkman light(=日の出後) フック: 明るい昼壁紙(霧の湖)へ切替。
# アクティブ画像を差し替えて hyprpaper を再起動 (IPC が hyprctl と非互換なため)。
W="$HOME/.local/share/wallpaper"
[ -f "$W/wallpaper-day.jpg" ] && cp -f "$W/wallpaper-day.jpg" "$W/wallpaper.jpg"
pkill -x hyprpaper 2>/dev/null || true
sleep 0.3
hyprpaper >/dev/null 2>&1 &
