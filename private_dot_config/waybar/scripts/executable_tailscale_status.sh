#!/usr/bin/env bash
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  jq -cn '{text:"󰖂",class:"off",tooltip:"tailscale not installed"}'
  exit 0
fi

status=$(tailscale status --json 2>/dev/null || echo '{}')
backend=$(echo "$status" | jq -r '.BackendState // "Unknown"')

if [[ "$backend" != "Running" ]]; then
  jq -cn --arg s "$backend" '{text:"󰖂",class:"off",tooltip:("Tailscale: "+$s)}'
  exit 0
fi

exit_id=$(echo "$status" | jq -r '.ExitNodeStatus.ID // empty')
self=$(echo "$status" | jq -r '.Self.HostName // "?"')

if [[ -n "$exit_id" ]]; then
  exit_host=$(echo "$status" | jq -r --arg id "$exit_id" '.Peer[] | select(.ID==$id) | .HostName // .DNSName' | head -1)
  short="${exit_host%%.*}"
  text="󰍂 ${short}"
  class="exit"
else
  text="󰖂"
  class="direct"
fi

peers=$(echo "$status" | jq -r '.Peer // {} | to_entries[] | .value | select(.Online==true) | "• \(.HostName) (\(.OS))"' | head -10)
[[ -z "$peers" ]] && peers="(no online peers)"

tooltip=$(printf 'Self: %s\nBackend: %s\nExit: %s\n\nOnline:\n%s' \
  "$self" "$backend" "${exit_host:-direct}" "$peers")

jq -cn --arg t "$text" --arg c "$class" --arg tip "$tooltip" \
  '{text:$t, class:$c, tooltip:$tip}'
