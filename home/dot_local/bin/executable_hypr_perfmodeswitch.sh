#!/usr/bin/env bash
# 既存の呼び出し元用。キー操作も同じ Hyprland 標準 Lua API を使う。
set -eu
hyprctl eval 'require("effects").toggle()'
