#!/bin/sh
# エージェントの状態を、ペイン metadata のトークン signal (電波の強さ) として報告する。
# 強さは本人の対応の急ぎ度。1 文字の高さで順序が分かり、色は config.toml の rules で付ける。
#   blocked (入力待ち) ▇   done (完了) ▅   working (作業中) ▃   idle (待機) ▁   unknown は消す
# 使い方: signal.sh event (イベントのフック) / signal.sh sync (全エージェント)
# どんな場合も exit 0 で終わり、herdr を止めない。
set -u

mode="${1:-event}"
source_id="dotfiles:agent-signal"
bin="${HERDR_BIN_PATH:-herdr}"
command -v jq >/dev/null 2>&1 || exit 0

report() { # pane_id status
  case "$2" in
    blocked) v='▇' ;;
    done) v='▅' ;;
    working) v='▃' ;;
    idle) v='▁' ;;
    *) v='' ;;
  esac
  if [ -n "$v" ]; then
    "$bin" pane report-metadata "$1" --source "$source_id" --token "signal=$v" >/dev/null 2>&1 || true
  else
    "$bin" pane report-metadata "$1" --source "$source_id" --clear-token signal >/dev/null 2>&1 || true
  fi
}

case "$mode" in
  sync)
    "$bin" agent list 2>/dev/null \
      | jq -r '.result.agents[]? | [.pane_id, (.agent_status // "")] | @tsv' 2>/dev/null \
      | while IFS="$(printf '\t')" read -r pane status; do
          [ -n "$pane" ] && report "$pane" "$status"
        done
    ;;
  *)
    json="${HERDR_PLUGIN_EVENT_JSON:-}"
    pane="$(printf '%s' "$json" | jq -r '.data.pane_id // .pane_id // empty' 2>/dev/null)"
    [ -n "$pane" ] || pane="${HERDR_PANE_ID:-}"
    [ -n "$pane" ] || exit 0
    status="$(printf '%s' "$json" | jq -r '.data.agent_status // .agent_status // empty' 2>/dev/null)"
    if [ -z "$status" ]; then
      status="$("$bin" agent get "$pane" 2>/dev/null | jq -r '.result.agent.agent_status // empty' 2>/dev/null)"
    fi
    report "$pane" "$status"
    ;;
esac
exit 0
