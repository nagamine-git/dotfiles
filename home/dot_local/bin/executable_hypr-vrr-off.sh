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
#
# Hyprland 0.57 (2026-11): .conf と `hyprctl keyword` が廃止された (keyword は unknown request を返す)。
#   monitors.lua の各 hl.monitor から output を読み、hyprctl eval で vrr = 0 を再適用する。
#   hl.monitor は同じ output の既存ルールへマージするので mode / position / scale は保たれる。
set -u

MON="$HOME/.config/hypr/monitors.lua"

# 念のためグローバルも 0 に (後勝ちで monitor 行の vrr が優先される)
hyprctl eval 'hl.config({ misc = { vrr = 0 } })' >/dev/null 2>&1

[ -f "$MON" ] || exit 0

# hl.monitor({ output = "NAME", ... }) の各行に vrr = 0 を再適用する。
grep -E '^[[:space:]]*hl\.monitor\(' "$MON" | while IFS= read -r line; do
  case "$line" in
    *"vrr ="*)           continue ;;  # 既に vrr 指定あり
    *"disabled = true"*) continue ;;  # 無効モニタはそのまま
  esac
  # output は "" (全出力) や空白を含む desc: もありえるので、引用符の中をそのまま取る
  output=$(printf '%s' "$line" | sed -E 's/.*output = "([^"]*)".*/\1/')
  hyprctl eval "hl.monitor({ output = \"$output\", vrr = 0 })" >/dev/null 2>&1
done

exit 0
