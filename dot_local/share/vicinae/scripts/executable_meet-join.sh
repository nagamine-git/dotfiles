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

# 開いてよい URL。カレンダーの招待は外部の誰でも送れるので、hangoutLink や会議の URL を
# そのまま xdg-open に渡さない (file://、javascript:、meet.google.com.evil.tld、
# meet.google.com@evil.tld などを開かされる)。Zoom など Meet 以外の会議も開かない。
# 同じ式を jq (\A と \z) と bash (^ と $) で文字列全体の先頭と末尾に固定して使う
MEET_URL='https://meet\.google\.com/[A-Za-z0-9_/?=&-]+'

# 会議のリンクがある予定を「開始 / 終了 / 題名 / Meet の URL」にする。区切りは \x1f
# (タブは read で空の欄が詰まるため)。リンクがあっても Meet の URL として通らなければ URL を空にする。
# 選ぶ前に弾くので、偽の予定が本物の予定を押しのけることは無い。自分 (self) が断った予定は候補にしない
rows=$(printf '%s' "$raw" | jq -r --arg re "\\A${MEET_URL}\\z" '
  (if type=="array" then .
   elif type=="object" and has("items") then .items
   elif type=="object" and has("events") then .events
   else [] end)
  | .[]?
  | select(any(.attendees[]?; type=="object" and .self == true and .responseStatus == "declined") | not)
  | ([.hangoutLink?, (.conferenceData?.entryPoints[]? | select(.entryPointType=="video") | .uri)]
     | map(select(type=="string" and . != ""))) as $links
  | select($links | length > 0)
  | (([$links[] | select(test($re))] | first) // "") as $url
  | ((.start.dateTime // .start.date // "")) as $start
  | select($start != "")
  | ((.end.dateTime // .end.date // $start)) as $end
  | (.summary // "(無題)") as $title
  | [$start, $end, $title, $url] | map(tostring | gsub("[\r\n\t\u001f]"; " ")) | join("\u001f")
') || {
  echo "予定の形式を読めませんでした"
  exit 1
}

# 終わってから 5 分以内のものも残し、開始がいちばん早いものを選ぶ (進行中があればそれになる)
now=$(date +%s)
best_start="" best_title="" best_url="" rejected=0
while IFS=$'\x1f' read -r start_raw end_raw title url; do
  [ -n "${start_raw:-}" ] || continue
  start=$(date -d "$start_raw" +%s 2>/dev/null) || continue
  end=$(date -d "${end_raw:-$start_raw}" +%s 2>/dev/null) || end=$((start + 1800))
  [ "$end" -ge $((now - 300)) ] || continue
  if [ -z "${url:-}" ]; then
    rejected=$((rejected + 1))
    continue
  fi
  if [ -z "$best_start" ] || [ "$start" -lt "$best_start" ]; then
    best_start=$start best_title=$title best_url=$url
  fi
done <<<"$rows"

if [ -z "$best_url" ]; then
  if [ "$rejected" -gt 0 ]; then
    echo "Meet 以外のリンクの予定は開きません ($rejected 件)"
  else
    echo "これからの Meet はありません"
  fi
  exit 0
fi

# 開く直前にもう一度確かめる
meet_re="^${MEET_URL}\$"
if ! [[ $best_url =~ $meet_re ]]; then
  echo "Meet の URL ではないので開きません"
  exit 1
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
