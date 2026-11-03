#!/usr/bin/env bash
# Claude Code の Stop フック。herdr のタブ名を、Claude Code が端末タイトルに出す作業内容の要約に合わせる。
# 変えるのは 1 ペインだけのタブで、名前が自動生成 (数字だけ) か前回このスクリプトが付けたものの場合に限る。
# 手で付けた名前は変えない。どんな場合も exit 0 で終わり、Claude Code を止めない。
# Wired in ~/.claude/settings.json -> hooks.Stop (herdr があるホストだけ)。
set -eu

cat >/dev/null 2>&1 || true

[ "${HERDR_ENV:-}" = "1" ] || exit 0
[ -n "${HERDR_PANE_ID:-}" ] || exit 0
command -v herdr >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0

max_chars=20

pane_json="$(herdr pane get "$HERDR_PANE_ID" 2>/dev/null)" || exit 0
# ペインは別のタブへ移動できるので、環境変数ではなくペインの現在の tab_id を使う
tab_id="$(printf '%s' "$pane_json" | jq -r '.result.pane.tab_id // empty' 2>/dev/null)" || exit 0
[ -n "$tab_id" ] || exit 0
# 文字数は jq がコードポイント単位で数えるので、マルチバイトの途中では切れない
title="$(printf '%s' "$pane_json" | jq -r --argjson max "$max_chars" '
  .result.pane.terminal_title_stripped // ""
  | gsub("\\p{Cc}"; "") | sub("^\\s+"; "") | sub("\\s+$"; "")
  | if length > $max then .[0:$max - 1] + "…" else . end' 2>/dev/null)" || exit 0

case "$title" in
  ''|'Claude Code'|'claude') exit 0 ;;
esac

tab_json="$(herdr tab get "$tab_id" 2>/dev/null)" || exit 0
pane_count="$(printf '%s' "$tab_json" | jq -r '.result.tab.pane_count // 0' 2>/dev/null)" || exit 0
label="$(printf '%s' "$tab_json" | jq -r '.result.tab.label // ""' 2>/dev/null)" || exit 0

# 分割ペインでは複数のエージェントがタブ名を取り合うので触らない
[ "$pane_count" = "1" ] || exit 0
[ "$label" != "$title" ] || exit 0

# 共有の /tmp には置かない。自分のものでないディレクトリやシンボリックリンクには書かない
state_dir="${XDG_RUNTIME_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}}/herdr-tab-title"
[ -d "$state_dir" ] || (umask 077 && mkdir -p "$state_dir") 2>/dev/null || true
[ -d "$state_dir" ] && [ ! -L "$state_dir" ] && [ -O "$state_dir" ] || exit 0
key="${tab_id//[^A-Za-z0-9._-]/_}"
state_file="$state_dir/$key"

case "$label" in
  ''|*[!0-9]*)
    prev=""
    if [ -f "$state_file" ] && [ ! -L "$state_file" ]; then
      prev="$(cat "$state_file" 2>/dev/null)" || prev=""
    fi
    [ -n "$prev" ] && [ "$label" = "$prev" ] || exit 0
    ;;
esac

herdr tab rename "$tab_id" "$title" >/dev/null 2>&1 || exit 0
[ ! -d "$state_file" ] || exit 0
tmp="$(mktemp "$state_dir/.$key.XXXXXX" 2>/dev/null)" || exit 0
if ! { printf '%s' "$title" >"$tmp" && mv -f "$tmp" "$state_file"; } 2>/dev/null; then
  rm -f "$tmp" 2>/dev/null || true
fi
exit 0
