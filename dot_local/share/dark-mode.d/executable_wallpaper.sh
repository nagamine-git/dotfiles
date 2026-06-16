#!/bin/sh
# darkman dark(=日没後) フック: 暗・暖色の夜壁紙(焚き火+星空)へ切替。
# hyprpaper IPC(v0.8.4)が hyprctl と非互換なため、アクティブ画像を差し替えて
# hyprpaper を再起動する。darkman フックはセッション内で走るので env を継承できる。
W="$HOME/.local/share/wallpaper"
[ -f "$W/wallpaper-night.jpg" ] && cp -f "$W/wallpaper-night.jpg" "$W/wallpaper.jpg"
pkill -x hyprpaper 2>/dev/null || true
sleep 0.3
hyprpaper >/dev/null 2>&1 &
# 夜壁紙は暗いので waybar も自動で暗テーマ(白文字/黒バー)へ
sleep 0.6
"$HOME/.local/bin/waybar-auto-theme.sh" "$W/wallpaper.jpg" >/dev/null 2>&1 || true
