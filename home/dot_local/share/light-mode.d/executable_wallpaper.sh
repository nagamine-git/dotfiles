#!/bin/sh
# darkman light(=日の出後) フック: 明るい昼壁紙(霧の湖)へ切替。
# アクティブ画像を差し替えて hyprpaper を再起動 (IPC が hyprctl と非互換なため)。
W="$HOME/.local/share/wallpaper"
[ -f "$W/wallpaper-day.jpg" ] && cp -f "$W/wallpaper-day.jpg" "$W/wallpaper.jpg"
# ロック画面の背景 (ぼかした壁紙) も作り直す
"$HOME/.local/bin/wallpaper-lock-image" >/dev/null 2>&1 || true
pkill -x hyprpaper 2>/dev/null || true
sleep 0.3
hyprpaper >/dev/null 2>&1 &
# waybar の島の色を新しい壁紙に合わせる (明るい壁紙では明るい島に反転、島ごとに壁紙の色相を帯びる)
"$HOME/.local/bin/waybar-wallpaper-tint" "$W/wallpaper.jpg" >/dev/null 2>&1 || true
