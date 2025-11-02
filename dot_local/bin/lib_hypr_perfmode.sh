# shellcheck shell=bash
# Shared Hyprland performance/normal mode keyword batches.

readonly HYPR_PERFORMANCE_BATCH=$(cat <<'EOF'
keyword animations:enabled false;
keyword decoration:blur:enabled false;
keyword decoration:shadow:enabled false;
keyword decoration:rounding 0;
keyword decoration:active_opacity 1;
keyword decoration:inactive_opacity 1;
keyword general:border_size 6;
keyword render:max_fps 60;
keyword general:gaps_in 0;
keyword general:gaps_out 0;
keyword decoration:multisample_edges false;
keyword cursor:animate false;
keyword misc:vrr on;
keyword misc:vfr true;
keyword misc:animate_manual_resizes false;
EOF
)

readonly HYPR_NORMAL_BATCH=$(cat <<'EOF'
keyword animations:enabled true;
keyword decoration:blur:enabled true;
keyword decoration:shadow:enabled true;
keyword decoration:rounding 8;
keyword decoration:active_opacity 1;
keyword decoration:inactive_opacity 0.8;
keyword general:border_size 1;
keyword render:max_fps 0;
keyword general:gaps_in 5;
keyword general:gaps_out 5;
keyword decoration:multisample_edges true;
keyword cursor:animate true;
keyword misc:vrr on;
keyword misc:vfr true;
keyword misc:animate_manual_resizes true;
EOF
)
