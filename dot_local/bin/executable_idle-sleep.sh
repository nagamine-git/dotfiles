#!/usr/bin/env bash
# Simple day/night idle sleep — called by hypridle after 30 min of inactivity.
#
# 規則:
#   1. 09:00–22:59 (service window) は寝ない
#   2. tailnet (100.64.0.0/10) に接続中 / リモート SSH 中なら寝ない
#   3. オーディオ再生中なら寝ない
#   3c. ノートが AC 給電中なら寝ない (WiFi は WoL 不可なので常時可達を優先)
#   3d. Claude Code の /loop がハートビートを打っていたら寝ない (TTL 付き)
#   3e. Claude Code のセッションが直近 N 分で CPU を使っていたら寝ない (TTL 付き)
#   4. それ以外 (= 23:00–08:59 で 30 分 AFK) → suspend (ノートはバッテリー時 hibernate)
#
# 過去に smart-idle-score.py / collector / 5 段 listener と heatmap で
# 学習させてみたが、保守コストに見合わなかったので時刻ベースに戻した。
set -euo pipefail

TAG=idle-sleep
hour=$(date +%H)

# Rule 1: service window
if [ "$hour" -ge 9 ] && [ "$hour" -lt 23 ]; then
    logger -t "$TAG" "STAY: service window ($hour:00–23:00)"
    exit 0
fi

# Rule 2: active tailnet TCP (someone reaching us via Tailscale)
if ss -tnH state established 2>/dev/null \
        | awk '$5 ~ /^100\./ {f=1; exit} END {exit !f}'; then
    logger -t "$TAG" "STAY: active tailnet connection"
    exit 0
fi

# Rule 2b: real remote SSH session (Remote=yes; local tmux panes excluded)
remote_n=$(loginctl list-sessions --no-legend 2>/dev/null \
    | awk '{print $1}' \
    | while read -r s; do
        loginctl show-session "$s" -p Remote --value 2>/dev/null
    done | grep -c '^yes$' || true)
if [ "${remote_n:-0}" -gt 0 ]; then
    logger -t "$TAG" "STAY: $remote_n remote session(s)"
    exit 0
fi

# Rule 3: audio / mic actively running (Zoom, mpv, music)
if command -v pactl >/dev/null 2>&1; then
    if pactl list sink-inputs 2>/dev/null \
            | grep -q "^[[:space:]]State: RUNNING"; then
        logger -t "$TAG" "STAY: audio playback"
        exit 0
    fi
    if pactl list source-outputs 2>/dev/null \
            | grep -q "^[[:space:]]State: RUNNING"; then
        logger -t "$TAG" "STAY: microphone in use"
        exit 0
    fi
fi

# Rule 3c: ノート (バッテリーあり) が AC 給電中なら寝ない。
# WiFi ノートは WoWLAN 非対応で外から WoL 起床できないため、自宅で AC 接続中は
# 寝かさず Tailscale 常時可達にしておく (= 外出先からはいつでも SSH 可)。
# 持ち出し時 (バッテリー駆動) は下の Rule 4 で suspend/hibernate。
# デスクトップ (バッテリー無し) はこの条件に該当せず、従来どおり nightly-suspend + WoL に委ねる。
if ls /sys/class/power_supply/BAT* >/dev/null 2>&1; then
    on_ac=0
    for f in /sys/class/power_supply/*/type; do
        [ -r "$f" ] || continue
        [ "$(cat "$f" 2>/dev/null)" = "Mains" ] || continue
        o="${f%/type}/online"
        if [ -r "$o" ] && [ "$(cat "$o" 2>/dev/null)" = "1" ]; then
            on_ac=1
            break
        fi
    done
    if [ "$on_ac" = "1" ]; then
        logger -t "$TAG" "STAY: laptop on AC (reachable mode)"
        exit 0
    fi
fi

# Rule 3d: Claude Code の /loop が回っている間は寝ない。
#
# loop は Bash を叩くだけで入力デバイスを触らないため、hypridle からは AFK に
# 見える。実際 2026-08-10 07:00 に "SUSPEND: hour=07, no veto" で落ち、
# GOLD LAB の巡回が朝まで止まった。
#
# **恒久的に夜間サスペンドを止めるのではなく、ハートビートの TTL で自然に
# 失効させる**。セッションが落ちたりマシンを放置したりすれば、TTL 経過後は
# いつもどおり寝る。止め忘れが事故にならないのが要点。
#
# 打つ側は loop の各巡回で:  touch "$XDG_RUNTIME_DIR/claude-loop.alive"
# /run/user 配下なので再起動で消える。止めたいときは rm するだけ。
HB="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/claude-loop.alive"
HB_TTL="${CLAUDE_LOOP_TTL:-5400}"          # 90分。loop の巡回間隔 (最大60分) より長く取る
if [ -f "$HB" ]; then
    hb_age=$(( $(date +%s) - $(stat -c %Y "$HB") ))
    if [ "$hb_age" -lt "$HB_TTL" ]; then
        logger -t "$TAG" "STAY: claude /loop heartbeat (${hb_age}s ago, ttl=${HB_TTL}s)"
        exit 0
    fi
    logger -t "$TAG" "claude /loop heartbeat が古い (${hb_age}s) — 無視して判定を続ける"
fi

# Rule 3e: Claude Code のセッションが直近 N 分で実際に働いていたら寝ない。
#
# Rule 3d のハートビートは /loop を回しているセッションしか打たない。通常の
# 対話セッションや、エージェントが長い作業を回しているだけのセッションは
# 無防備で、2026-08-23 07:00 に稼働中のセッションごと落ちた。
#
# claude-cpu-watch.timer (60 秒ごと) が comm=="claude" の CPU 使用を監視し、
# 実作業レベルの消費を見つけたときだけ claude-active.alive を touch する。
# ここではその鮮度だけを見る。単に開いているだけのセッションは CPU を
# ほとんど使わないのでスタンプが古くなり、いつもどおり寝る。
ACT="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/claude-active.alive"
ACT_TTL="${CLAUDE_ACTIVE_TTL:-900}"        # 15分。長いツール実行や API 待ちで
                                           # CPU が途切れる谷を跨げる長さ。
if [ -f "$ACT" ]; then
    act_age=$(( $(date +%s) - $(stat -c %Y "$ACT") ))
    if [ "$act_age" -lt "$ACT_TTL" ]; then
        logger -t "$TAG" "STAY: claude session active (${act_age}s ago, ttl=${ACT_TTL}s)"
        exit 0
    fi
    logger -t "$TAG" "claude session activity が古い (${act_age}s) — 無視して判定を続ける"
fi

# Rule 4: suspend (hibernate on battery)
bat_status=""
for f in /sys/class/power_supply/BAT*/status; do
    [ -r "$f" ] && bat_status="$(cat "$f")" && break
done
if [ "$bat_status" = "Discharging" ]; then
    logger -t "$TAG" "HIBERNATE: laptop on battery (hour=$hour)"
    exec systemctl hibernate
fi
logger -t "$TAG" "SUSPEND: hour=$hour, no veto"
exec systemctl suspend
