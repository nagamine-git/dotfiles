#!/bin/sh
# 直前の workspace に戻る。戻ると track.sh が current と previous を入れ替えるので、続けて押すと往復する。
# 閉じられた workspace なら focus が失敗するだけで害はない。
set -eu

previous="$HERDR_PLUGIN_STATE_DIR/previous"
[ -f "$previous" ] || exit 0
prev="$(cat "$previous")"
exec "$HERDR_BIN_PATH" workspace focus "$prev"
