# shellcheck shell=bash
# Shared Hyprland performance/normal mode batches.
# Hyprland 0.57 の Lua 設定では `hyprctl keyword` が使えないので、1 行ずつ hl.config を eval する。
# render:max_fps / decoration:multisample_edges / cursor:animate / misc:vfr は 0.56 の時点で
# 既に存在せず効いていなかったので移していない。
# VRR は 4K@120Hz HDMI でパネルが黒落ちするため常時オフ (config 既定 vrr=0)。

# shellcheck disable=SC2034 # source 先 (hypr_perfmodeswitch.sh など) が使う
readonly HYPR_PERFORMANCE_BATCH=$(cat <<'EOF'
eval hl.config({ animations = { enabled = false } });
eval hl.config({ decoration = { blur = { enabled = false } } });
eval hl.config({ decoration = { shadow = { enabled = false } } });
eval hl.config({ decoration = { rounding = 0 } });
eval hl.config({ decoration = { active_opacity = 1 } });
eval hl.config({ decoration = { inactive_opacity = 1 } });
eval hl.config({ general = { border_size = 6 } });
eval hl.config({ general = { gaps_in = 0 } });
eval hl.config({ general = { gaps_out = 0 } });
eval hl.config({ misc = { vrr = 0 } });
eval hl.config({ misc = { animate_manual_resizes = false } })
EOF
)

# shellcheck disable=SC2034 # source 先 (hypr_perfmodeswitch.sh など) が使う
readonly HYPR_NORMAL_BATCH=$(cat <<'EOF'
eval hl.config({ animations = { enabled = true } });
eval hl.config({ decoration = { blur = { enabled = true } } });
eval hl.config({ decoration = { shadow = { enabled = true } } });
eval hl.config({ decoration = { rounding = 8 } });
eval hl.config({ decoration = { active_opacity = 1 } });
eval hl.config({ decoration = { inactive_opacity = 0.8 } });
eval hl.config({ general = { border_size = 1 } });
eval hl.config({ general = { gaps_in = 5 } });
eval hl.config({ general = { gaps_out = 5 } });
eval hl.config({ misc = { vrr = 0 } });
eval hl.config({ misc = { animate_manual_resizes = true } })
EOF
)
