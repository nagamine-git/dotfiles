#!/usr/bin/env bash
# セキュリティ更新チェック (Arch 専用)。
# 公式更新数 + AUR更新数 + arch-audit(修正版が出たCVE) + 最終 full upgrade 時刻 を集計し、
#   1) claude-notify で通知し、
#   2) state ファイル (~/.local/state/security-update-check/status) へ書き出す。
# state ファイルは .zshrc が起動時に「読むだけ」で警告表示するための高速キャッシュ。
# 起動トリガ: systemd --user timer (週次, 保険) と、.zshrc の 24h 超チェック (裏で実行)。
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

# 最終 full system upgrade の時刻 (epoch)。zsh 側で「更新滞留」(14日/30日) 判定に使う。
# ローリング Arch では「保留更新の有無」は常に真で無意味なため、最後に -Syu した時刻で測る。
last_upgrade=0
if [ -r /var/log/pacman.log ]; then
  ts="$(grep -F 'starting full system upgrade' /var/log/pacman.log 2>/dev/null | tail -n1 \
        | sed -n 's/^\[\([0-9T:+-]*\)\].*/\1/p')"
  [ -n "$ts" ] && last_upgrade="$(date -d "$ts" +%s 2>/dev/null || echo 0)"
fi

# state ファイルへ書き出し。1 行目は機械可読 (zsh が読む)、以降は人間向けメッセージ。
# mtime が「最後にチェックした時刻」= zsh の 24h 再実行判定にも使う。
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/security-update-check"
mkdir -p "$state_dir"
{
  printf 'upd=%s aur=%s vuln=%s last_upgrade=%s\n' "${upd:-0}" "${aur:-0}" "${vuln:-0}" "${last_upgrade:-0}"
  printf '%s\n' "$msg"
} > "$state_dir/status"

if command -v claude-notify >/dev/null 2>&1 && [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
  claude-notify security-update "$msg" >/dev/null 2>&1 || true
fi
printf '%s\n' "$msg"
