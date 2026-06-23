#!/usr/bin/env bash
# 週次セキュリティ更新チェック (Arch 専用)。
# 公式更新数 + AUR更新数 + arch-audit(CVE/要対応) を集計し、claude-notify で通知する。
# systemd --user timer (security-update-check.timer) から oneshot 起動される。
# paru/checkupdates/arch-audit が無くても落ちないよう全て存在チェック付き。
set -uo pipefail
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

upd=0
if command -v checkupdates >/dev/null 2>&1; then
  upd="$(checkupdates 2>/dev/null | grep -c . || true)"
fi

aur=0
if command -v paru >/dev/null 2>&1; then
  aur="$(paru -Qua 2>/dev/null | grep -c . || true)"
fi

vuln_list=""
vuln=0
if command -v arch-audit >/dev/null 2>&1; then
  # -u: 修正版が出ているもののみ / -q: パッケージ名だけ
  vuln_list="$(arch-audit -uq 2>/dev/null || true)"
  vuln="$(printf '%s' "$vuln_list" | grep -c . || true)"
fi

msg="公式更新 ${upd} / AUR ${aur} / 要対応CVE ${vuln}"
if [ "${vuln:-0}" -gt 0 ]; then
  pkgs="$(printf '%s' "$vuln_list" | head -8 | tr '\n' ' ')"
  msg="${msg}"$'\n'"脆弱: ${pkgs}"
fi

if command -v claude-notify >/dev/null 2>&1 && [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
  claude-notify security-update "$msg" >/dev/null 2>&1 || true
fi
printf '%s\n' "$msg"
