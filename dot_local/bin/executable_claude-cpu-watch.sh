#!/usr/bin/env bash
# Claude Code (CLI) が実際に働いているかを CPU 使用量で判定し、
# 働いていればスタンプファイルを touch する。idle-sleep.sh がこれを見る。
#
# なぜ必要か:
#   Claude Code はキーボード/マウスを触らないので hypridle からは完全な AFK に
#   見える。2026-08-23 07:00 に稼働中セッションごと SUSPEND した (ログ:
#   "SUSPEND: hour=07, no veto")。従来の対策は /loop 専用のハートビート
#   (claude-loop.alive) だけで、通常の対話セッションは何も守っていなかった。
#
# 方式:
#   systemd user timer から SAMPLE_SEC 秒ごとに呼ばれ、comm == "claude" の
#   プロセス群の累積 CPU time (utime+stime) を前回スナップショットと比較する。
#   閾値を超えたプロセスが 1 つでもあればスタンプを touch。
#   idle-sleep.sh はスタンプの鮮度 (TTL) だけを見る = 既存の claude-loop.alive
#   と同じ「TTL で自然失効する」設計。放置しても事故にならないのが要点。
#
# 設計上の注意:
#   - 単純な pgrep にしない。起動して放置しているだけのセッションでも永久に
#     寝なくなるため。CPU を根拠に「開いてるだけ」と「実際に動いてる」を分ける。
#   - 全プロセスの delta を *合算しない*。アイドルのセッションも Node の
#     イベントループで常時わずかに CPU を使うため、セッション数が増えるほど
#     合計が閾値を超えてしまう。「最も忙しい 1 プロセス」で判定する。
set -euo pipefail

RUNTIME="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
STATE="$RUNTIME/claude-cpu-watch.state"
STAMP="$RUNTIME/claude-active.alive"

# 閾値: 60 秒あたりの CPU ticks (CLK_TCK=100 なので 1 tick = 10ms)。
# 実測値に基づく — 末尾の「閾値の根拠」を参照。
# 実際のサンプル間隔は 60 秒ちょうどとは限らないので、下で経過時間に正規化する。
THRESHOLD_TICKS="${CLAUDE_CPU_THRESHOLD_TICKS:-150}"

# 前回サンプルからの経過時間がこの範囲外なら比較せず基準を取り直す。
# 下限: 間隔が短すぎると 1 tick の量子化誤差でレートが暴れる。
# 上限: suspend/resume やタイマー停止を跨いだ差分は「その間ずっと働いていた」
#       ことを意味しないので、復帰直後に誤ってスタンプを打たないようにする。
MIN_ELAPSED="${CLAUDE_CPU_MIN_ELAPSED:-20}"
MAX_ELAPSED="${CLAUDE_CPU_MAX_ELAPSED:-300}"

# comm == "claude" のみ対象。claude-desktop / claude.exe (chrome native host) /
# claude-usage-notify は常駐して CPU を使い続けるので除外する。
snapshot() {
    local p pid st rest
    for p in /proc/[0-9]*; do
        pid=${p#/proc/}
        [ -r "$p/comm" ] || continue
        [ "$(cat "$p/comm" 2>/dev/null)" = "claude" ] || continue
        st=$(cat "$p/stat" 2>/dev/null) || continue
        rest=${st##*') '}          # comm の閉じ括弧より後ろ = state 以降
        # shellcheck disable=SC2086
        set -- $rest
        # 元の stat での utime(14) stime(15) は rest では 12, 13 番目
        echo "$pid $(( ${12} + ${13} ))"
    done
}

# 前回サンプル時刻は state ファイルの mtime で持つ (別途書かなくて済む)。
prev_ts=0
[ -s "$STATE" ] && prev_ts=$(stat -c %Y "$STATE" 2>/dev/null || echo 0)

snapshot | sort -k1,1 > "$STATE.new"
now_ts=$(stat -c %Y "$STATE.new")
elapsed=$(( now_ts - prev_ts ))

# 比較できない状況 (初回 / 間隔が短すぎ or 長すぎ) では基準を取り直すだけ。
if [ "$prev_ts" -eq 0 ] || [ "$elapsed" -lt "$MIN_ELAPSED" ] \
        || [ "$elapsed" -gt "$MAX_ELAPSED" ]; then
    mv "$STATE.new" "$STATE"
    exit 0
fi

# 前回と今回を突き合わせて「最も CPU を使ったプロセス」の delta を求め、
# 60 秒あたりのレートに正規化する。
# 前回に居なかった pid (= 新しく起動したセッション) は起動処理で必ず CPU を
# 使うので、累積値をそのまま delta とみなして活動扱いにする。
max_rate=$(awk -v elapsed="$elapsed" '
    NR == FNR { prev[$1] = $2; next }
    {
        d = ($1 in prev) ? $2 - prev[$1] : $2
        if (d > max) max = d
    }
    END { printf "%d\n", (max + 0) * 60 / elapsed }
' "$STATE" "$STATE.new")

mv "$STATE.new" "$STATE"

if [ "$max_rate" -ge "$THRESHOLD_TICKS" ]; then
    touch "$STAMP"
fi

# 閾値の根拠 (2026-08-23 am5-itx 実測, 60 秒サンプル, CLK_TCK=100):
#   アイドル (プロンプト待ち) のセッション : 32–45 ticks/60s (≒ 0.5–0.75% CPU)
#   実作業中のセッション                   : 371–610 ticks/60s (≒ 6–10% CPU)
# 150 ticks/60s (= 2.5% CPU 相当) は底ノイズの約 3 倍、実作業の約 1/2.5 で、
# 両者の谷のほぼ中央。サンプル間隔を変えるならこの値も比例させること。
