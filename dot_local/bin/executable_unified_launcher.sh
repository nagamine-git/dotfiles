#!/usr/bin/env bash
set -euo pipefail

# Unified launcher (Raycast/Spotlight-like) for Wayland/Hyprland using wofi
# - Search apps (desktop entries)
# - Switch to windows
# - Jump to workspaces
# - Common actions (lock, logout, power)
# Usage: bind to Super+Space in Hyprland

wofi_cmd=(wofi --dmenu --prompt "何でも検索" --insensitive)

# Minimal debug helper (opt-in): UNIFIED_LAUNCHER_DEBUG=1
log_debug() {
  [ "${UNIFIED_LAUNCHER_DEBUG:-0}" = "1" ] || return 0
  local logfile="/tmp/unified_launcher.log"
  printf "[%s] %s\n" "$(date '+%F %T')" "$*" >> "$logfile" 2>/dev/null || true
}

have_cmd() { command -v "$1" >/dev/null 2>&1; }

# Dump Hyprland clients as TSV: address, wsid, class, initialClass, title, mapped, hidden
dump_clients_tsv() {
  have_cmd hyprctl || return 0
  have_cmd jq || return 0
  local raw
  if [ "${UNIFIED_LAUNCHER_DEBUG:-0}" = "1" ]; then
    raw=$(hyprctl clients -j 2>/dev/null | tee /tmp/unified_launcher.clients.json)
  else
    raw=$(hyprctl clients -j 2>/dev/null)
  fi
  printf '%s' "$raw" | jq -r '
    (if type=="array" then .[] else . end)
    | select(type=="object")
    | [ (.address // ""), (.workspace?.id // ""), (.class // ""), (.initialClass // ""), (.title // ""), (.mapped // false), (.hidden // false) ]
    | @tsv' | tee /tmp/unified_launcher.clients.tsv >/dev/null 2>&1 || true
}

is_launcher_running() {
  # Detect our wofi instance by prompt text
  pgrep -a wofi 2>/dev/null | grep -F -- "--dmenu" | grep -F -- "何でも検索" >/dev/null 2>&1
}

toggle_close_if_running() {
  if is_launcher_running; then
    # Gracefully close existing wofi instances matching our prompt
    pgrep -a wofi | grep -F -- "--dmenu" | grep -F -- "何でも検索" | awk '{print $1}' | xargs -r kill
    log_debug "Closed existing launcher instance"
    exit 0
  fi
}

focus_or_launch() {
  local id="$1" name="$2" wmclass="$3"
  log_debug "focus_or_launch id='$id' name='$name' wmclass='$wmclass'"

  if have_cmd hyprctl && have_cmd jq; then
    local addr idbase
    idbase=${id%.desktop}
    dump_clients_tsv >/dev/null || true
    # 1) Exact WMClass match
    if [ -n "${wmclass:-}" ]; then
      addr=$(awk -F '\t' -v c="$wmclass" '$6=="true" { if($3==c || $4==c){print $1; exit} }' /tmp/unified_launcher.clients.tsv)
    fi
    # 2) Title contains Name (case-insensitive)
    if [ -z "${addr:-}" ] && [ -n "${name:-}" ]; then
      addr=$(awk -F '\t' -v n="$name" 'BEGIN{IGNORECASE=1} $6=="true" && index($5,n){print $1; exit}' /tmp/unified_launcher.clients.tsv)
    fi
    # 3) Class equals/contains desktop idbase
    if [ -z "${addr:-}" ] && [ -n "${idbase:-}" ]; then
      addr=$(awk -F '\t' -v i="$idbase" 'BEGIN{IGNORECASE=1} $6=="true" { if($3==i || $4==i || index($3,i) || index($4,i)){print $1; exit} }' /tmp/unified_launcher.clients.tsv)
    fi
    if [ -n "${addr:-}" ]; then
      log_debug "Focusing existing window at address: $addr"
      hyprctl dispatch focuswindow "address:$addr"
      return 0
    else
      log_debug "No existing window match; launching: $id"
    fi
  else
    log_debug "hyprctl/jq not available; launching: $id"
  fi

  if have_cmd gtk-launch; then
    gtk-launch "$id" & disown
  else
    # Fallback: try to locate the desktop file Exec and run it
    local desktop
    for d in "$HOME/.local/share/applications" "/usr/local/share/applications" "/usr/share/applications"; do
      desktop="$d/$id"
      if [ -f "$desktop" ]; then
        local exec_line
        exec_line=$(grep -m1 '^Exec=' "$desktop" | sed 's/^Exec=//') || true
        if [ -n "${exec_line:-}" ]; then
          log_debug "Executing from Exec in desktop: $exec_line"
          bash -lc "$exec_line" & disown
          return 0
        fi
      fi
    done
    notify-send "Launcher" "起動できませんでした: $id"
  fi
}

escape_arg() { sed "s/'/'\\''/g"; }

list_apps() {
  # List desktop files and show as selectable entries
  # We route execution via this script to allow focus-or-launch behavior
  local dirs=("$HOME/.local/share/applications" "/usr/local/share/applications" "/usr/share/applications")
  for d in "${dirs[@]}"; do
    [ -d "$d" ] || continue
    while IFS= read -r -d '' f; do
      local id name wmclass
      id=$(basename "$f")
      # Prefer localized Name= if present; fallback to first Name=
      name=$(grep -m1 -E '^(Name\[[^]]+\]|Name)=' "$f" | head -n1 | sed 's/^Name\(\[[^]]\+\]\)\?=//') || true
      [ -n "${name:-}" ] || name="${id%.desktop}"
      wmclass=$(grep -m1 '^StartupWMClass=' "$f" | sed 's/^StartupWMClass=//') || true
      # Escape for single-quoted shell args
      name_esc=$(printf %s "$name" | escape_arg)
      wmclass_esc=$(printf %s "${wmclass:-}" | escape_arg)
      printf "[APP] %s || ~/.local/bin/unified_launcher.sh --focus-or-launch '%s' '%s' '%s'\n" \
        "$name" "$id" "$name_esc" "${wmclass_esc:-}"
    done < <(find "$d" -maxdepth 1 -type f -name '*.desktop' -print0 2>/dev/null)
  done
}

list_windows() {
  dump_clients_tsv || return 0
  awk -F '\t' '
    function trim(s){ sub(/^ +/,"",s); sub(/ +$/,"",s); return s }
    BEGIN{OFS=""}
    $6=="true" {
      ws=$2; if(ws=="") ws="-";
      t=$5; t=trim(t); if(t=="") t=(($3!="")?$3:(($4!="")?$4:"No Title"));
      addr=$1;
      print "[WIN] ", t, " [", ws, "] || hyprctl dispatch focuswindow \"address:", addr, "\""
    }
  ' /tmp/unified_launcher.clients.tsv | tee /tmp/unified_launcher.windows.txt
}

list_workspaces() {
  have_cmd hyprctl || return 0
  have_cmd jq || return 0
  hyprctl workspaces -j | jq -r '.[] | "[WS] \(.id) || hyprctl dispatch workspace \(.id)"'
}

# Cache app list to speed up repeated opens (optional)
cache_apps_list() {
  local cache_file="$HOME/.cache/unified_launcher.apps"
  local ttl="${UNIFIED_LAUNCHER_APPS_TTL:-300}" # seconds
  mkdir -p "$HOME/.cache"
  if [ -f "$cache_file" ]; then
    local now mtime age
    now=$(date +%s)
    mtime=$(date +%s -r "$cache_file" 2>/dev/null || echo 0)
    age=$(( now - mtime ))
    if [ "$age" -lt "$ttl" ]; then
      cat "$cache_file"
      return 0
    fi
  fi
  list_apps | tee "$cache_file"
}

# Free-text selection fallback: try to focus by title/class, else launch matching desktop
focus_or_launch_query() {
  local query="$1"
  log_debug "focus_or_launch_query: '$query'"
  # Try focus by title/class substring match first
  if have_cmd hyprctl && have_cmd jq; then
    local addr
    dump_clients_tsv >/dev/null || true
    addr=$(awk -F '\t' -v q="$query" 'BEGIN{IGNORECASE=1} $6=="true" { if(index($5,q) || index($3,q) || index($4,q)){print $1; exit} }' /tmp/unified_launcher.clients.tsv)
    if [ -n "${addr:-}" ]; then
      log_debug "Focus by query matched address: $addr"
      hyprctl dispatch focuswindow "address:$addr"
      return 0
    fi
  fi
  # Then try to find a matching desktop file by Name or ID
  local id name wmclass
  read -r id name wmclass < <(find_desktop_by_name "$query" || true)
  if [ -n "${id:-}" ]; then
    log_debug "Launching via desktop match: id=$id name=$name wmclass=$wmclass"
    focus_or_launch "$id" "$name" "$wmclass"
    return 0
  fi
  notify-send "Launcher" "見つかりませんでした: $query"
}

# Find desktop by name substring (case-insensitive). Prints: id name wmclass
find_desktop_by_name() {
  local q="$1"
  local dirs=("$HOME/.local/share/applications" "/usr/local/share/applications" "/usr/share/applications")
  for d in "${dirs[@]}"; do
    [ -d "$d" ] || continue
    while IFS= read -r -d '' f; do
      local id name wmclass base
      id=$(basename "$f")
      base=${id%.desktop}
      name=$(grep -m1 -E '^(Name\[[^]]+\]|Name)=' "$f" | head -n1 | sed 's/^Name\(\[[^]]\+\]\)\?=//') || true
      wmclass=$(grep -m1 '^StartupWMClass=' "$f" | sed 's/^StartupWMClass=//') || true
      if printf '%s\n%s\n' "$name" "$base" | grep -iF "$q" >/dev/null 2>&1; then
        printf '%s\t%s\t%s\n' "$id" "${name:-$base}" "${wmclass:-}"
        return 0
      fi
    done < <(find "$d" -maxdepth 1 -type f -name '*.desktop' -print0 2>/dev/null)
  done
  return 1
}

list_actions() {
  cat <<'EOF'
[ACTION] Lock screen || hyprlock
[ACTION] Notification Center || swaync-client -t -sw
[ACTION] Toggle Perf Mode || ~/.local/bin/hypr_perfmodeswitch.sh
[ACTION] Clipboard History || bash -lc 'cliphist list | wofi --dmenu --prompt="📋 選択→貼り付け" | cliphist decode | wl-copy && sleep 0.1 && wtype -M ctrl v'
[ACTION] Search Apps… (drun) || wofi --show drun --prompt "アプリ検索"
[ACTION] Run Command… || wofi --show run --prompt "コマンド実行"
[ACTION] Power: Logout (Hyprland) || hyprctl dispatch exit
[ACTION] Power: Reboot || systemctl reboot
[ACTION] Power: Shutdown || systemctl poweroff
EOF
}

main() {
  # Toggle behavior: if already open, close it and exit
  toggle_close_if_running
  # Subcommand mode: focus-or-launch
  if [ "${1:-}" = "--focus-or-launch" ]; then
    shift
    local id name wmclass
    id=${1:-}
    name=${2:-}
    wmclass=${3:-}
    focus_or_launch "$id" "$name" "$wmclass"
    exit 0
  fi

  # Build candidates (robust to env differences)
  # Note: order matters; windows first for quick switching, then apps
  tmp=$(mktemp)
  tmp2=$(mktemp)
  {
    log_debug "Gathering windows"
    list_windows || true
    log_debug "Gathering workspaces"
    list_workspaces || true
    log_debug "Gathering actions"
    list_actions || true
    # Fast mode by default: skip heavy full-app indexing unless enabled
    if [ "${UNIFIED_LAUNCHER_INCLUDE_APPS:-0}" = "1" ]; then
      log_debug "Gathering apps (may be heavy)"
      cache_apps_list || list_apps || true
    else
      log_debug "Skipping full apps list (UNIFIED_LAUNCHER_INCLUDE_APPS!=1)"
    fi
  } >"$tmp" 2>/dev/null || true

  # Strip empty lines; de-dup if awk exists
  local pre_count post_count
  pre_count=$(wc -l < "$tmp" | tr -d ' ')
  if [ "${UNIFIED_LAUNCHER_DEBUG:-0}" = "1" ]; then
    log_debug "Raw tmp lines: $pre_count"
    log_debug "Raw WIN lines: $(grep -c '^\[WIN\]' "$tmp" || true)"
  fi
  if have_cmd awk; then
    grep -v '^[[:space:]]*$' "$tmp" | awk '!seen[$0]++' > "$tmp2" || true
  else
    grep -v '^[[:space:]]*$' "$tmp" > "$tmp2" || true
  fi
  post_count=$(wc -l < "$tmp2" | tr -d ' ')
  log_debug "Items before dedup: $pre_count, after: $post_count"
  mapfile -t items < "$tmp2" || true
  if [ "${UNIFIED_LAUNCHER_DEBUG:-0}" = "1" ]; then
    printf '%s\n' "${items[@]}" > /tmp/unified_launcher.items.txt
    log_debug "Materialized items saved to /tmp/unified_launcher.items.txt"
  fi
  rm -f "$tmp" "$tmp2" || true

  # Always provide at least Actions as fallback
  if [ ${#items[@]} -eq 0 ]; then
    log_debug "Primary list empty; falling back to actions only"
    mapfile -t items < <(list_actions) || true
  fi

  # Present menu
  if [ ${#items[@]} -eq 0 ]; then
    notify-send "Launcher" "候補がありません"
    log_debug "Still empty after fallback"
    exit 0
  fi

  # Build mapping: assign numeric IDs to avoid showing commands (prevents markup issues)
  map_file=$(mktemp)
  disp_file=$(mktemp)
  id=0
  for line in "${items[@]}"; do
    [ -n "$line" ] || continue
    label=${line%%|| *}
    cmd_part=""
    if printf '%s' "$line" | grep -F '||' >/dev/null 2>&1; then
      cmd_part=${line#*|| }
    fi
    id=$((id+1))
    printf '%d\t%s\n' "$id" "$cmd_part" >> "$map_file"
    printf '%03d %s\n' "$id" "$label" >> "$disp_file"
  done

  selection=$(cat "$disp_file" | "${wofi_cmd[@]}") || { log_debug "No selection or wofi canceled"; rm -f "$map_file" "$disp_file"; exit 0; }

  # Extract numeric id prefix
  sel_id=$(printf '%s' "$selection" | awk '{print $1}')
  if printf '%s' "$sel_id" | grep -Eq '^[0-9]+$'; then
    cmd=$(awk -v id="$sel_id" -F '\t' '$1==id {print substr($0, index($0,$2))}' "$map_file" | head -n1)
    rm -f "$map_file" "$disp_file"
    if [ -n "${cmd:-}" ]; then
      log_debug "Executing (id=$sel_id): $cmd"
      bash -lc "$cmd" & disown
      exit 0
    fi
  fi
  rm -f "$map_file" "$disp_file"
  # Fallback: treat as free-text query
  log_debug "Treating selection as query: $selection"
  # Remove leading numeric if user edited
  q=$(printf '%s' "$selection" | sed 's/^[0-9]\+ *//')
  focus_or_launch_query "$q"
  exit 0

}

main "$@"
