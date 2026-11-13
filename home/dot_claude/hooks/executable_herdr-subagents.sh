#!/usr/bin/env bash
# Claude Code の SubagentStart / SubagentStop / SessionStart フック。実行中のサブエージェントの数と種類を、
# herdr のペイン metadata のトークン subagents (例: ⧗2 coder, Explore) として報告する。
# サイドバーに出すには herdr の config.toml の rows_by_agent に "$subagents" を書く。
# SessionStart では前のセッションの残りを消す。compact は settings の matcher で外す (同じセッションが続くため)。
# Stop では消さない (バックグラウンドのサブエージェントが動き続けるため)。
# イベントは引数 (start / stop / session) か stdin の hook_event_name で判定する。
# どんな場合も exit 0 で終わり、Claude Code を止めない。
# Wired in ~/.claude/settings.json -> hooks.SubagentStart / SubagentStop / SessionStart (herdr があるホストだけ)。
set -eu

input="$(cat 2>/dev/null)" || input=""

[ "${HERDR_ENV:-}" = "1" ] || exit 0
[ -n "${HERDR_PANE_ID:-}" ] || exit 0
command -v herdr >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0
# 並行して届く開始と終了を直列にするのに使う。無いホスト (macOS の既定) では何もしない
command -v flock >/dev/null 2>&1 || exit 0

source_id="dotfiles:claude-subagents"
# herdr のサイドバーの既定幅は 26 桁
max_chars=22

event="${1:-}"
if [ -z "$event" ]; then
  event="$(printf '%s' "$input" | jq -r '.hook_event_name // empty' 2>/dev/null)" || exit 0
fi
case "$event" in
  start|SubagentStart) action=start ;;
  stop|SubagentStop) action=stop ;;
  session|SessionStart) action=session ;;
  *) exit 0 ;;
esac

agent_id="$(printf '%s' "$input" | jq -r '.agent_id // empty' 2>/dev/null)" || exit 0
case "$action" in
  # サブエージェントの中から来た SessionStart で、親の一覧を消さない
  session) [ -z "$agent_id" ] || exit 0 ;;
  *) [ -n "$agent_id" ] || exit 0 ;;
esac

agent_type=""
if [ "$action" = "start" ]; then
  agent_type="$(printf '%s' "$input" | jq -r '
    .agent_type // "" | gsub("\\p{Cc}"; "") | if . == "" then "agent" else . end' 2>/dev/null)" || exit 0
fi

# 共有の /tmp には置かない。自分のものでないディレクトリやシンボリックリンクには書かない
state_dir="${XDG_RUNTIME_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}}/herdr-subagents"
[ -d "$state_dir" ] || (umask 077 && mkdir -p "$state_dir") 2>/dev/null || true
[ -d "$state_dir" ] && [ ! -L "$state_dir" ] && [ -O "$state_dir" ] || exit 0

key="${HERDR_PANE_ID//[^A-Za-z0-9._-]/_}"
state_file="$state_dir/$key.json"
lock_file="$state_dir/$key.lock"

[ ! -L "$lock_file" ] || exit 0
{ exec 9>>"$lock_file"; } 2>/dev/null || exit 0
# 報告もロックの中で行い、herdr に届く順番を状態ファイルの更新順と揃える
flock -w 4 9 || exit 0

state='[]'
if [ -f "$state_file" ] && [ ! -L "$state_file" ]; then
  state="$(jq -c 'if type == "array" then . else [] end' "$state_file" 2>/dev/null)" || state='[]'
  [ -n "$state" ] || state='[]'
fi

case "$action" in
  start)
    state="$(printf '%s' "$state" | jq -c --arg id "$agent_id" --arg type "$agent_type" '
      map(select(.id != $id)) + [{id: $id, type: $type}]' 2>/dev/null)" || exit 0
    ;;
  stop)
    state="$(printf '%s' "$state" | jq -c --arg id "$agent_id" 'map(select(.id != $id))' 2>/dev/null)" || exit 0
    ;;
  session)
    state='[]'
    ;;
esac

if [ "$state" = '[]' ]; then
  rm -f "$state_file" 2>/dev/null || true
else
  [ ! -d "$state_file" ] || exit 0
  tmp="$(mktemp "$state_dir/.$key.XXXXXX" 2>/dev/null)" || exit 0
  if ! { printf '%s\n' "$state" >"$tmp" && mv -f "$tmp" "$state_file"; } 2>/dev/null; then
    rm -f "$tmp" 2>/dev/null || true
    exit 0
  fi
fi

# 種類は開始順に並べ、同じ種類が複数あれば ×N を付ける。文字数は jq がコードポイント単位で数える
summary="$(printf '%s' "$state" | jq -r --argjson max "$max_chars" '
  length as $n
  | if $n == 0 then "" else
      (reduce .[].type as $t ({order: [], count: {}};
          (if .count[$t] == null then .order += [$t] else . end) | .count[$t] += 1)
        | [.order[] as $t | $t + (if .count[$t] > 1 then "×\(.count[$t])" else "" end)]
        | join(", ")) as $types
      | "⧗\($n) \($types)"
      | if length > $max then .[0:$max - 1] + "…" else . end
    end' 2>/dev/null)" || exit 0

# TTL は付けない。フックが来ない間は延長できず、長く動くサブエージェントの表示が途中で消えるため。
# ペイン ID は --source より前に置く (herdr 0.9.5 は後ろに置くと引数を取り違える)
if [ -n "$summary" ]; then
  herdr pane report-metadata "$HERDR_PANE_ID" --source "$source_id" --token "subagents=$summary" >/dev/null 2>&1 || exit 0
else
  herdr pane report-metadata "$HERDR_PANE_ID" --source "$source_id" --clear-token subagents >/dev/null 2>&1 || exit 0
fi
exit 0
