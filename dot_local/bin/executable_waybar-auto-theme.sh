#!/usr/bin/env bash
# 壁紙の「waybar が乗る上部ストリップ」の平均輝度で waybar の配色を自動切替する。
#   明るい上部 → 黒文字 / 明るいバー / 白影
#   暗い上部   → 白文字 / 暗いバー / 黒影 (既定)
# style.css の @define-color 3 行を sed で書き換え、waybar を SIGUSR2 でリロードする。
# 起動時 (hyprland.conf exec-once) と壁紙変更時 (引数で新パスを渡す) に呼ぶ想定。
# 失敗しても waybar 起動を妨げないよう、どのスキップ経路でも exit 0 で抜ける。
set -uo pipefail

STYLE="$HOME/.config/waybar/style.css"
HYPRPAPER="$HOME/.config/hypr/hyprpaper.conf"

# 壁紙パス: 引数 > hyprpaper.conf の path > 既定
WALL="${1:-}"
if [ -z "$WALL" ] && [ -f "$HYPRPAPER" ]; then
  WALL="$(grep -E '^[[:space:]]*path[[:space:]]*=' "$HYPRPAPER" | head -1 | sed 's/.*=[[:space:]]*//' | tr -d ' ')"
fi
[ -z "$WALL" ] && WALL="$HOME/.local/share/wallpaper/wallpaper.jpg"

[ -f "$STYLE" ] || { echo "style.css なし: $STYLE" >&2; exit 0; }
[ -f "$WALL" ]  || { echo "wallpaper なし: $WALL"  >&2; exit 0; }
command -v magick >/dev/null 2>&1 || { echo "magick なし (スキップ)" >&2; exit 0; }

# 上部 8% ストリップの平均輝度 (0.0=暗 .. 1.0=明)
lum="$(magick "$WALL" -gravity North -crop '100%x8%+0+0' +repage \
        -colorspace Gray -resize 1x1 -format '%[fx:mean]' info: 2>/dev/null)"
[ -n "$lum" ] || { echo "輝度測定失敗 (スキップ)" >&2; exit 0; }

# しきい値 0.55 で明暗判定
if awk -v l="$lum" 'BEGIN{exit !(l>0.55)}'; then
  fg="#1a1a1a"; bg="rgba(236, 238, 241, 0.82)"; sh="rgba(255, 255, 255, 0.55)"; mode="light(黒文字/白バー)"
else
  fg="#b7bcba"; bg="rgba(22, 23, 25, 0.85)";    sh="rgba(0, 0, 0, 0.70)";       mode="dark(白文字/黒バー)"
fi

sed -i \
  -e "s|^@define-color wbfg .*|@define-color wbfg $fg;|" \
  -e "s|^@define-color wbbg .*|@define-color wbbg $bg;|" \
  -e "s|^@define-color wbsh .*|@define-color wbsh $sh;|" \
  "$STYLE"

# 起動中なら即リロード (起動時はまだ waybar が無いので skip → 立ち上げ時に新 CSS を読む)
if pgrep -x waybar >/dev/null 2>&1; then
  killall -SIGUSR2 waybar 2>/dev/null || true
fi

logger -t waybar-auto-theme "lum=$lum -> $mode ($WALL)" 2>/dev/null || true
exit 0
