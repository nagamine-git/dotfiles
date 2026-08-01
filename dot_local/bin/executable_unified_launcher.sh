#!/usr/bin/env bash
set -euo pipefail

# Unified launcher (Raycast/Spotlight-like) for Wayland/Hyprland using rofi.
# - Search apps (desktop entries), switch windows, jump workspaces, common actions,
#   and surface upcoming Google Meet events (via gog)
# - Bound to Super+Space in Hyprland
#
# This single file plays two roles:
#   1) Trigger: invoked directly by the keybind. Toggles a rofi popup.
#   2) Rofi "script mode" backend: invoked BY rofi (ROFI_RETV is set) to produce
#      the candidate list, and again on selection to act on it.
#
# Rows are emitted using rofi's row-option syntax (see rofi-script(5)):
#   <label>\0icon\x1f<icon>\x1fdisplay\x1f<pango markup>\x1fmeta\x1f<hidden terms>\x1finfo\x1f<command>
#   - label   : what fuzzy matching runs against, and what the user reads
#   - display : same text plus a dim category tag (markup); NOT searched
#   - meta    : invisible extra search terms, so "アプリ"/"app" narrow by category
#   - info    : the command to run, handed back via $ROFI_INFO on selection.
#     Carrying the command here means selection does NOT rebuild the candidate
#     list (which would re-scan every .desktop file just to throw it away).

SCRIPT_PATH="$HOME/.local/bin/unified_launcher.sh"
MODI_NAME="unified"
WINDOW_TITLE="unified-launcher"

# 補助テキスト色。config.rasi の fg-dim と同値 (AA 4.56:1)。
# ここは pango markup なのでテーマ変数を参照できず、同期は手動。
TAG_COLOR="#7d8791"

ICON_MEET="call-start"
ICON_WS="user-desktop"
ICON_WIN_FALLBACK="preferences-system-windows"
ICON_APP_FALLBACK="application-x-executable"
ICON_LOCK="system-lock-screen"
ICON_NOTIFY="preferences-system-notifications"
ICON_PERF="view-refresh"
ICON_CLIP="edit-copy"
ICON_RUN="system-search"
ICON_CALC="accessories-calculator"
ICON_EMOJI="face-smile"
ICON_LOGOUT="system-log-out"
ICON_REBOOT="system-reboot"
ICON_SHUTDOWN="system-shutdown"

declare -A ICON_BY_CLASS

log_debug() {
  [ "${UNIFIED_LAUNCHER_DEBUG:-0}" = "1" ] || return 0
  printf "[%s] %s\n" "$(date '+%F %T')" "$*" >> /tmp/unified_launcher.log 2>/dev/null || true
}

have_cmd() { command -v "$1" >/dev/null 2>&1; }
escape_arg() { sed "s/'/'\\''/g"; }

# pango markup 用のエスケープ。ウィンドウタイトルには & や < が実際に現れる。
# 注意点2つ:
#  - & を最初に処理しないと二重エスケープになる
#  - bash 5.2 以降は置換文字列中の素の & が「マッチした文字列」を意味するため、
#    \& と書かないと < が &lt; ではなく <lt; になる
pango_escape() {
  local s="$1"
  s="${s//&/\&amp;}"
  s="${s//</\&lt;}"
  s="${s//>/\&gt;}"
  printf '%s' "$s"
}

# 1行を rofi の row-option 形式で出力する
# emit_row <label> <icon> <tag> <meta> <command>
emit_row() {
  local label="$1" icon="$2" tag="$3" meta="$4" cmd="$5"
  local disp
  disp="$(pango_escape "$label")"
  if [ -n "$tag" ]; then
    disp+="   <span foreground=\"$TAG_COLOR\" size=\"small\">$(pango_escape "$tag")</span>"
  fi
  printf '%s\0icon\x1f%s\x1fdisplay\x1f%s\x1fmeta\x1f%s\x1finfo\x1f%s\n' \
    "$label" "$icon" "$disp" "$meta" "$cmd"
}

# Dump Hyprland clients as TSV: address, wsid, class, initialClass, title, mapped, hidden
dump_clients_tsv() {
  have_cmd hyprctl || return 0
  have_cmd jq || return 0
  hyprctl clients -j 2>/dev/null | jq -r '
    (if type=="array" then .[] else . end)
    | select(type=="object")
    | [ (.address // ""), (.workspace?.id // ""), (.class // ""), (.initialClass // ""), (.title // ""), (.mapped // false), (.hidden // false) ]
    | @tsv' > /tmp/unified_launcher.clients.tsv 2>/dev/null || true
}

is_launcher_running() {
  pgrep -af rofi 2>/dev/null | grep -F -- "-window-title $WINDOW_TITLE" >/dev/null 2>&1
}

toggle_close_if_running() {
  if is_launcher_running; then
    pgrep -af rofi | grep -F -- "-window-title $WINDOW_TITLE" | awk '{print $1}' | xargs -r kill
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
    if [ -n "${wmclass:-}" ]; then
      addr=$(awk -F '\t' -v c="$wmclass" '$6=="true" { if($3==c || $4==c){print $1; exit} }' /tmp/unified_launcher.clients.tsv)
    fi
    if [ -z "${addr:-}" ] && [ -n "${name:-}" ]; then
      addr=$(awk -F '\t' -v n="$name" 'BEGIN{IGNORECASE=1} $6=="true" && index($5,n){print $1; exit}' /tmp/unified_launcher.clients.tsv)
    fi
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

# Free-text fallback: try to focus by title/class, else launch matching desktop
focus_or_launch_query() {
  local query="$1"
  log_debug "focus_or_launch_query: '$query'"
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
  local id name wmclass
  read -r id name wmclass < <(find_desktop_by_name "$query" || true) || true
  if [ -n "${id:-}" ]; then
    log_debug "Launching via desktop match: id=$id name=$name wmclass=$wmclass"
    focus_or_launch "$id" "$name" "$wmclass"
    return 0
  fi
  notify-send "Launcher" "見つかりませんでした: $query"
}

# .desktop を1回走査して (a) アプリ行 (b) ウィンドウ用アイコン索引 を同時に作る。
# ウィンドウ行が索引に依存するのでアプリ行の出力は最後に回す必要があるが、
# 行を変数に溜めるのは不可: 行区切りに NUL を使っており $(...) が NUL を捨ててしまう
# (「ヌルバイトを無視しました」警告と共に label と icon が繋がって壊れる)。
# そのため一時ファイルに退避する。
APP_ROWS_FILE=""
cleanup() { [ -n "$APP_ROWS_FILE" ] && rm -f "$APP_ROWS_FILE"; }

# 抽出は awk の1パスにまとめる。ファイルごとに basename/grep/sed/tr を起動していた
# 頃はここだけで 0.5 秒近くかかっていた (.desktop 約100件 × 7プロセス)。
# 同じ理由でシェル側のクォート処理も sed ではなく bash 内蔵の置換で行う。
build_desktop_index() {
  local dirs=() d id name wmclass icon name_esc wmclass_esc cmd
  for d in "$HOME/.local/share/applications" "/usr/local/share/applications" "/usr/share/applications"; do
    [ -d "$d" ] && dirs+=("$d")
  done
  APP_ROWS_FILE=$(mktemp)
  trap cleanup EXIT
  [ ${#dirs[@]} -gt 0 ] || return 0

  # 区切りは \x1e。タブは IFS 上「空白類」扱いなので連続タブが1つに畳まれてしまい、
  # StartupWMClass が無いアプリで icon が wmclass 側にずれる
  while IFS=$'\x1e' read -r id name wmclass icon; do
    [ -n "$id" ] || continue
    [ -n "$wmclass" ] && ICON_BY_CLASS["${wmclass,,}"]="$icon"
    name_esc=${name//\'/\'\\\'\'}
    wmclass_esc=${wmclass//\'/\'\\\'\'}
    cmd="$SCRIPT_PATH --focus-or-launch '$id' '$name_esc' '$wmclass_esc'"
    emit_row "$name" "$icon" "アプリ" "アプリ app ${id%.desktop}" "$cmd" >> "$APP_ROWS_FILE"
  done < <(
    find "${dirs[@]}" -maxdepth 1 -type f -name '*.desktop' -print0 2>/dev/null |
      xargs -0 -r gawk -v fallback="$ICON_APP_FALLBACK" '
        FNR==1 { name=""; wm=""; icon="" }
        # 各キーは最初に現れたものを採用する。.desktop は [Desktop Entry] が先頭に
        # 来るので、後続の [Desktop Action ...] 内の Name= に上書きされない
        name=="" && /^Name(\[[^]]*\])?=/ { s=$0; sub(/^[^=]*=/,"",s); name=s }
        wm==""   && /^StartupWMClass=/   { s=$0; sub(/^[^=]*=/,"",s); wm=s }
        icon=="" && /^Icon=/             { s=$0; sub(/^[^=]*=/,"",s); icon=s }
        ENDFILE {
          n=split(FILENAME,p,"/"); base=p[n]
          if (name=="") { name=base; sub(/\.desktop$/,"",name) }
          if (icon=="") icon=fallback
          gsub(/[\t\r\036]/," ",name); gsub(/[\t\r\036]/," ",wm); gsub(/[\t\r\036]/," ",icon)
          print base "\036" name "\036" wm "\036" icon
        }'
  )
}

# Google Calendar の直近イベントから Meet リンク付きを抽出。
# - 短い TTL でキャッシュ (UNIFIED_LAUNCHER_MEETS_TTL 秒, default 90)
# - gog 未認証 / API 失敗時は静かに 0 行 (ランチャー全体は壊さない)
# - 終了済み(5分猶予)は除外。「進行中」「N分後」「時刻」の3段階表示
# キャッシュには生の TSV (label/url) を保存し、行の組み立ては毎回行う。
# そうしないと相対時刻 ("15分後") がキャッシュされて古い値を表示してしまう。
list_meets() {
  have_cmd gog || return 0
  have_cmd jq || return 0

  local cache_file="$HOME/.cache/unified_launcher.meets.tsv"
  local ttl="${UNIFIED_LAUNCHER_MEETS_TTL:-90}"
  mkdir -p "$HOME/.cache"

  local fresh=0
  if [ -f "$cache_file" ]; then
    local now mtime
    now=$(date +%s)
    mtime=$(date +%s -r "$cache_file" 2>/dev/null || echo 0)
    [ $(( now - mtime )) -lt "$ttl" ] && fresh=1
  fi

  if [ "$fresh" = "0" ]; then
    local raw
    raw=$(timeout 3s gog cal events --days=2 --max 12 -j --results-only 2>/dev/null) || raw=""
    : > "$cache_file"
    if [ -n "$raw" ]; then
      printf '%s' "$raw" | jq -r '
        (if type=="array" then .
         elif type=="object" and has("items") then .items
         elif type=="object" and has("events") then .events
         else [] end)
        | .[]?
        | ((.hangoutLink // "")) as $hl
        | (([.conferenceData?.entryPoints[]? | select(.entryPointType=="video") | .uri] | first) // "") as $cl
        | (if $hl != "" then $hl elif $cl != "" then $cl else "" end) as $url
        | select($url != "")
        | ((.start.dateTime // .start.date // "")) as $start
        | ((.end.dateTime // .end.date // $start)) as $end
        | ((.summary // "(無題)") | gsub("[\\r\\n\\t]"; " ")) as $title
        | [$start, $end, $title, $url] | @tsv
      ' > "$cache_file" 2>/dev/null || : > "$cache_file"
    fi
  fi

  local now_epoch start_raw end_raw title url
  now_epoch=$(date +%s)
  while IFS=$'\t' read -r start_raw end_raw title url; do
    [ -n "${url:-}" ] || continue
    local start_epoch end_epoch diff_min rel
    start_epoch=$(date -d "$start_raw" +%s 2>/dev/null) || continue
    end_epoch=$(date -d "${end_raw:-$start_raw}" +%s 2>/dev/null) || end_epoch=$((start_epoch + 1800))
    [ "$end_epoch" -ge $((now_epoch - 300)) ] || continue
    if [ "$start_epoch" -le "$now_epoch" ]; then
      rel="進行中"
    else
      diff_min=$(( (start_epoch - now_epoch) / 60 ))
      if [ "$diff_min" -lt 60 ]; then
        rel="${diff_min}分後"
      else
        rel=$(date -d "@$start_epoch" +%H:%M 2>/dev/null)
      fi
    fi
    emit_row "$rel  $title" "$ICON_MEET" "会議" "会議 meet ミーティング" "xdg-open \"$url\""
  done < "$cache_file"
}

list_windows() {
  dump_clients_tsv || return 0
  [ -f /tmp/unified_launcher.clients.tsv ] || return 0
  local addr ws cls icls title mapped hidden t key icon
  while IFS=$'\t' read -r addr ws cls icls title mapped hidden; do
    [ "$mapped" = "true" ] || continue
    t=$(printf %s "$title" | tr -d '\t\n')
    [ -n "$t" ] || t="${cls:-${icls:-No Title}}"
    [ -n "$ws" ] || ws="-"
    key="${cls:-$icls}"
    icon="${ICON_BY_CLASS[${key,,}]:-$ICON_WIN_FALLBACK}"
    # label にはワークスペース番号を残す: 同名タイトルが別ワークスペースに
    # 並んだときに見分けがつかなくなるのを防ぐ
    emit_row "$t [$ws]" "$icon" "ウィンドウ" "ウィンドウ window $key" \
      "hyprctl dispatch focuswindow \"address:$addr\""
  done < /tmp/unified_launcher.clients.tsv
}

list_workspaces() {
  have_cmd hyprctl || return 0
  have_cmd jq || return 0
  local id
  while read -r id; do
    [ -n "$id" ] || continue
    emit_row "ワークスペース $id" "$ICON_WS" "移動" "ワークスペース workspace ws 移動" \
      "hyprctl dispatch workspace $id"
  done < <(hyprctl workspaces -j 2>/dev/null | jq -r '.[].id' 2>/dev/null || true)
}

list_actions() {
  local clip_cmd
  clip_cmd='cliphist list | rofi -dmenu -p "貼り付け" | cliphist decode | wl-copy && sleep 0.1 && wtype -M ctrl v'
  emit_row "ロック画面"          "$ICON_LOCK"     "操作" "操作 action lock ロック" "hyprlock"
  emit_row "通知センター"        "$ICON_NOTIFY"   "操作" "操作 action notification 通知" "swaync-client -t -sw"
  emit_row "パフォーマンスモード切替" "$ICON_PERF" "操作" "操作 action perf performance" "~/.local/bin/hypr_perfmodeswitch.sh"
  emit_row "クリップボード履歴"  "$ICON_CLIP"     "操作" "操作 action clipboard クリップボード" "bash -lc '$clip_cmd'"
  emit_row "コマンド実行…"       "$ICON_RUN"      "操作" "操作 action run exec コマンド" "rofi -show run"
  emit_row "電卓"                "$ICON_CALC"     "操作" "操作 action calc calculator 計算" "rofi -show calc -modi calc"
  emit_row "絵文字ピッカー"      "$ICON_EMOJI"    "操作" "操作 action emoji 絵文字" "rofi -show emoji -modi emoji"
  emit_row "サインアウト"        "$ICON_LOGOUT"   "電源" "電源 power logout サインアウト" "hyprctl dispatch exit"
  emit_row "再起動"              "$ICON_REBOOT"   "電源" "電源 power reboot 再起動" "systemctl reboot"
  emit_row "シャットダウン"      "$ICON_SHUTDOWN" "電源" "電源 power shutdown 電源オフ" "systemctl poweroff"
}

# rofi の script-mode バックエンド (ROFI_RETV が設定されている時)
modi_mode() {
  local retv="${ROFI_RETV:-0}"

  # 選択された: コマンドは ROFI_INFO で渡ってくるので候補を作り直さない
  if [ "$retv" = "1" ] || [ "$retv" = "2" ]; then
    local cmd="${ROFI_INFO:-}"
    if [ -n "$cmd" ]; then
      log_debug "Executing: $cmd"
      bash -lc "$cmd" >/dev/null 2>&1 &
      disown
    else
      # info の無い行 = 自由入力
      focus_or_launch_query "${1:-}"
    fi
    return 0
  fi

  # 初回呼び出し: 候補一覧を出す
  printf '\0markup-rows\x1ftrue\n'
  # フッターのキーヒント。各行右端の番号バッジ (element-index) と対応する
  printf '\0message\x1f<span size="small">%s</span>\n' \
    'Alt+1〜0 その行へ直接ジャンプ    ↵ 実行    Esc 閉じる'
  build_desktop_index          # ICON_BY_CLASS を埋め、アプリ行を一時ファイルへ
  list_meets || true
  list_windows || true         # ICON_BY_CLASS に依存するので index の後
  list_workspaces || true
  list_actions || true
  cat "$APP_ROWS_FILE"
}

main() {
  if [ -n "${ROFI_RETV:-}" ]; then
    modi_mode "$@"
    exit 0
  fi

  if [ "${1:-}" = "--focus-or-launch" ]; then
    shift
    focus_or_launch "${1:-}" "${2:-}" "${3:-}"
    exit 0
  fi

  toggle_close_if_running
  exec rofi -show "$MODI_NAME" -modi "$MODI_NAME:$SCRIPT_PATH" -window-title "$WINDOW_TITLE"
}

main "$@"
