#!/bin/sh
# VRR黒落ち対策: 起動時にモニタへ VRR=off を「明示パラメータ」で再適用する。
#
# 背景 (2026-06-22 調査):
#   config に misc{vrr=0} はあり、lib_hypr_perfmode.sh の両バッチも `keyword misc:vrr 0` を
#   打つが、いずれも効かず am5-itx の 4K@120Hz HDMI でパネルが黒落ちした。原因は2つ:
#     1) hyprland.conf は `source=monitors.conf`(モニタ初期化) が misc{} ブロックより前に
#        評価されるため、モニタ初期化時点では vrr=0 がまだ適用されていない。
#     2) `hyprctl keyword misc:vrr 0` 単体では、初期化済みモニタへ再適用されないと反映されない
#        (実証: keyword では vrr:true のまま、monitor 再適用で初めて vrr:false になった)。
#   そこで monitors.conf (nwg-displays 生成・vrr 指定なし) の各 monitor 行に vrr,0 を付けて
#   再適用し、モニタ個別 VRR を確実にオフにする。vrr,0 は VRR非対応モニタでも無害なので全マシン安全。
set -u

MON="$HOME/.config/hypr/monitors.conf"

# 念のためグローバルも 0 に (後勝ちで monitor 行の vrr が優先される)
hyprctl keyword misc:vrr 0 >/dev/null 2>&1

[ -f "$MON" ] || exit 0

# monitor=NAME,RES,POS,SCALE[,...] の各行に vrr,0 を付与して再適用する。
grep -E '^[[:space:]]*monitor[[:space:]]*=' "$MON" | while IFS= read -r line; do
  val=$(printf '%s' "${line#*=}" | tr -d ' ')
  case "$val" in
    "")            : ;;                                            # 空
    *,vrr,*)       hyprctl keyword monitor "$val"        >/dev/null 2>&1 ;;  # 既に vrr 指定あり
    *disable*)     hyprctl keyword monitor "$val"        >/dev/null 2>&1 ;;  # 無効モニタはそのまま
    *)             hyprctl keyword monitor "${val},vrr,0" >/dev/null 2>&1 ;;  # vrr,0 を付与
  esac
done

exit 0
