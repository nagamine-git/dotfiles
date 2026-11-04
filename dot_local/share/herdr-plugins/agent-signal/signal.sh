#!/bin/sh
# 電波アイコンとワークスペース名を 1 つの値にして、ペイン metadata のトークン signal_workspace として報告する。
# herdr は値と値の間に必ず " · " を入れるので、まとめることでアイコンと名前の間の区切りを無くしている。
# アイコンは Nerd Font の md-signal_cellular_*。本数が本人の対応の急ぎ度で、色は state_icon が持つ。
#   blocked (入力待ち) U+F08BE 󰢾   done (完了) U+F08BD 󰢽   working (作業中) U+F08BC 󰢼   idle (待機) U+F08BF 󰢿   unknown はアイコンなしで名前だけ
# 対応表は config.toml の [ui.sidebar.agents] のコメントと揃える。
# どのイベントでも全エージェントを今の状態から作り直し、値が変わるペインにだけ報告する。名前を取得できないペインは既存の値を変えない。
# 旧トークン signal が残っていれば消す。どんな場合も exit 0 で終わり、herdr を止めない。
set -u

source_id="dotfiles:agent-signal"
bin="${HERDR_BIN_PATH:-herdr}"
command -v jq >/dev/null 2>&1 || exit 0

{ "$bin" agent list; "$bin" workspace list; } 2>/dev/null \
  | jq -rs '
      {blocked: "󰢾", done: "󰢽", working: "󰢼", idle: "󰢿"} as $icons
      | ((.[1].result.workspaces // []) | map({key: .workspace_id, value: .label}) | from_entries) as $labels
      | (.[0].result.agents // [])[]
      | ($labels[.workspace_id] // "") as $label
      | select($label != "")
      | ($icons[.agent_status // ""] // "") as $icon
      | (if $icon == "" then $label else "\($icon) \($label)" end) as $value
      | select($value != .tokens.signal_workspace or .tokens.signal != null)
      | "\(.pane_id)\t\($value)"' 2>/dev/null \
  | while IFS="$(printf '\t')" read -r pane value; do
      "$bin" pane report-metadata "$pane" --source "$source_id" \
        --token "signal_workspace=$value" --clear-token signal >/dev/null 2>&1 || true
    done
exit 0
