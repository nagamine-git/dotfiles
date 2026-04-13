#!/usr/bin/env bash
set -euo pipefail

pkill -f "ccr start" 2>/dev/null || true

ccr start &
CCR_PID=$!

trap 'kill "$CCR_PID" 2>/dev/null || true' EXIT INT TERM

sleep 2
ccr code "$@"
