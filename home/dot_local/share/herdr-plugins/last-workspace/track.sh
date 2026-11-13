#!/bin/sh
# workspace.focused のたびに呼ばれ、今の workspace を current、その前の workspace を previous に残す。
set -eu

id="$(printf '%s' "$HERDR_PLUGIN_EVENT_JSON" | jq -r '.data.workspace_id // empty')"
[ -n "$id" ] || exit 0

current="$HERDR_PLUGIN_STATE_DIR/current"
if [ -f "$current" ]; then
  [ "$(cat "$current")" != "$id" ] || exit 0
  mv -f "$current" "$HERDR_PLUGIN_STATE_DIR/previous"
fi
printf '%s\n' "$id" >"$current"
