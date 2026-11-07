#!/usr/bin/env bash
# @vicinae.schemaVersion 1
# @vicinae.title Meet に参加
# @vicinae.mode silent
# @vicinae.icon 📹
# @vicinae.keywords ["meet", "google meet", "会議", "ミーティング"]
# @vicinae.description 進行中か次に始まる Google Meet を開く。予定は gog で Google カレンダーから読む
set -eu

# Vicinae のスクリプトコマンド (~/.local/share/vicinae/scripts)。旧 unified_launcher.sh の会議の行の代わり。
# silent モードは標準出力の 1 行目を HUD に出し、失敗 (終了コード 0 以外) なら 1 行目をトーストに出す。
# Vicinae は 10 秒で打ち切るので、gog の待ち時間はそれより短くする。

# Hyprland から起動した Vicinae の PATH には ~/.local/bin (gog の置き場所) が入っていない
PATH="$HOME/.local/bin:$PATH"

for cmd in gog jq; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "$cmd が見つかりません"
    exit 1
  fi
done

if ! raw=$(timeout 8s gog cal events --days=2 --max 12 -j --results-only 2>/dev/null); then
  echo "予定を読めませんでした (gog の認証を確認)"
  exit 1
fi

# Meet のリンクがある予定を「開始 / 終了 / 題名 / URL」の TSV にする
rows=$(printf '%s' "$raw" | jq -r '
  (if type=="array" then .
   elif type=="object" and has("items") then .items
   elif type=="object" and has("events") then .events
   else [] end)
  | .[]?
  | ((.hangoutLink // "")) as $hl
  | (([.conferenceData?.entryPoints[]? | select(.entryPointType=="video") | .uri] | first) // "") as $cl
  | (if $hl != "" then $hl elif $cl != "" then $cl else "" end) as $url
  | select($url != "")
  | ((.start.dateTime // .start.date // "")) as $start
  | ((.end.dateTime // .end.date // $start)) as $end
  | ((.summary // "(無題)") | gsub("[\\r\\n\\t]"; " ")) as $title
  | [$start, $end, $title, $url] | @tsv
') || {
  echo "予定の形式を読めませんでした"
  exit 1
}

# 終わってから 5 分以内のものも残し、開始がいちばん早いものを選ぶ (進行中があればそれになる)
now=$(date +%s)
best_start="" best_title="" best_url=""
while IFS=$'\t' read -r start_raw end_raw title url; do
  [ -n "${url:-}" ] || continue
  start=$(date -d "$start_raw" +%s 2>/dev/null) || continue
  end=$(date -d "${end_raw:-$start_raw}" +%s 2>/dev/null) || end=$((start + 1800))
  [ "$end" -ge $((now - 300)) ] || continue
  if [ -z "$best_start" ] || [ "$start" -lt "$best_start" ]; then
    best_start=$start best_title=$title best_url=$url
  fi
done <<<"$rows"

if [ -z "$best_url" ]; then
  echo "これからの Meet はありません"
  exit 0
fi

if [ "$best_start" -le "$now" ]; then
  rel="進行中"
elif [ $(((best_start - now) / 60)) -lt 60 ]; then
  rel="$(((best_start - now) / 60))分後"
elif [ "$(date -d "@$best_start" +%F)" = "$(date +%F)" ]; then
  rel=$(date -d "@$best_start" +%H:%M)
else
  rel=$(date -d "@$best_start" +'%-m/%-d %H:%M')
fi

# ブラウザが Vicinae の出力のパイプを握ったまま残らないよう、切り離して起動する
setsid -f xdg-open "$best_url" >/dev/null 2>&1
echo "$rel  $best_title"
