---
name: daily-focus
description: 今日やるべきタスクTOP5を GitHub PR / Notion / Gmail / Slack「あとで」から自動抽出・重複統合・スコアリングし、対話確認の上で Google Calendar に60分ブロックを作る。朝のフォーカス時間設計に使う。
---

# Daily Focus (TOP5 + Calendar Block)

朝に1回走らせる前提。マルチソース(GitHub / Notion / Gmail / Slack「あとで」)から **今日処理すべきタスクTOP5** を抽出し、Google Calendar の `tsuyoshi.nagamine@efg-technologies.com` に60分ブロックを5件作成する。

## 前提

- ソース: GitHub PR(`gh`)、Notion DB(efg-technologies workspace)、Gmail(MCP)、Slack「あとで」(`is:saved`)
- カレンダー: `tsuyoshi.nagamine@efg-technologies.com`
- Notion DB URL: `https://www.notion.so/efg-technologies/0909084359734678bee409df8d109411?v=19f9d7b305e04d23b479074bb167105d`

## 重み付け基準

| ソース | 種別 | weight |
|---|---|---:|
| Notion | 期限切れ | 5 |
| GitHub | assignee=me の open PR(自分が作業) | 4 |
| Notion | 期限=今日/明日 | 3 |
| GitHub | open PR で未レビュー(他者から依頼) | 3 |
| Slack | 「あとで」(is:saved) 保存 | 3 |
| Gmail | AI判定で「要対応」 | 2 |
| Notion | 期限=2-3日後 | 2 |
| GitHub | involves:@me で未レビュー(全般) | 1 |

複数ソース重複ヒット時は **重み合算** (例: 同タスクがNotion期限切れ+PR割り当て=5+4=9)。

---

## 手順

### 1. 認証・前提確認 (並行)

```bash
date '+%Y-%m-%d %A'  # 今日の日付/曜日
gh auth status 2>&1 | head -3
```

並行で:
- `mcp__notion__notion-search` で Notion 認証確認
- `mcp__google-workspace__list_calendars` で Google Workspace 認証確認
- `mcp__plugin_slack_slack__slack_search_public_and_private` で Slack 認証確認 (query="is:saved" limit=1)

未認証ならユーザに通知して中断。

### 2. データ取得 (並行)

#### A. GitHub PR (3クエリ)

```bash
# Q1 (weight 4): 自分が作業者
gh search prs --json url,title,repository,updatedAt,number,state \
  'updated:>@today-1y sort:updated-desc is:open is:private involves:@me is:pr assignee:@me -org:co-nect' \
  --limit 30

# Q2 (weight 3): 他者から依頼、未レビュー (PR限定)
gh search prs --json url,title,repository,updatedAt,number,state,author \
  'updated:>@today-1y sort:updated-desc is:private is:open involves:@me -reviewed-by:@me is:pr -org:co-nect' \
  --limit 30

# Q3 (weight 1): involves全般 (PR+Issue) 未レビュー
gh search issues --json url,title,repository,updatedAt,number,state,author \
  'updated:>@today-1y sort:updated-desc is:private is:open involves:@me -reviewed-by:@me -org:co-nect' \
  --limit 30
```

assignee=me ヒット件は Q2/Q3 から除外して二重計上を防ぐ(URLで重複排除)。

#### B. Notion DB

`mcp__notion__notion-fetch` で DB を取得し、各ページの `due_date` プロパティで分類:
- `due < 今日` → 期限切れ (weight 5)
- `今日 <= due <= 明日` → weight 3
- `明日 < due <= 今日+3日` → weight 2
- それ以外 → 対象外

ステータスが「完了」「Done」「Closed」等のものは除外。

#### C. Gmail (24h未読 全件AI判定)

```
mcp__google-workspace__search_gmail_messages
  query: "is:unread newer_than:1d in:inbox"
  user_google_email: "tsuyoshi.nagamine@efg-technologies.com"
```

`get_gmail_messages_content_batch` で件名・送信者・本文先頭を取得し、各件を以下に分類:

- **要対応**: 返信/承認/期限あるアクションが必要 → weight 2
- **情報のみ**: 読むだけで完了する情報通知 → 除外
- **不要/spam**: ニュースレター・販促・通知 → 除外

判定基準:
- 個人宛(to=自分) の依頼/質問 → 要対応
- 期日付き請求書・契約・税務関係 → 要対応
- GitHub/Notion等のサービス通知 → 別ソースと重複なので除外
- メルマガ・販促・ダイジェスト → 除外

#### D. Slack「あとで」(is:saved)

```
mcp__plugin_slack_slack__slack_search_public_and_private
  query: "is:saved"
  sort: "timestamp"
  sort_dir: "desc"
  limit: 20
  include_context: false
```

各ヒットを weight 3 で候補に追加。タスク名は本文先頭60文字、出典URLはSlackのpermalinkを使う。
本文がリンクのみ/極端に短い場合は、リンク先(NotionやGitHub)が他ソースと重複する可能性が高いので統合フェーズで吸収する。

### 3. 重複統合

各候補をフラット化した上で、以下のキーで統合:

- 同じURLが本文・リンクに含まれる(Gmail通知 ↔ Notion/PR)
- タイトルの正規化(空白・記号・大文字小文字)で部分一致
- 言及されているIssue/PR番号(#123)で一致

統合時は **重みを合算** し、出典を全て保持(タスク詳細に併記)。

### 4. スコアリング & TOP5抽出

```
score = 重み合計 + (期限緊急度ボーナス: 期限切れ +2, 今日 +1)
```

- スコア降順でソート
- 上位5件を抽出
- 同スコアの場合は: ① Notion期限近い ② PR更新新しい ③ Gmail新しい の順

### 5. 対話的確認

以下の表で TOP5 を提示:

```
| # | タスク | 出典 | 期限/状態 | 推定60min |
|---|--------|------|-----------|-----------|
| 1 | xxx    | Notion(期限切れ) + PR#42 | 2026-04-28(2日超過) | OK |
| ... |
```

ユーザに `AskUserQuestion` で確認:
- そのままCalendarブロック作成 / 差し替え / 中止

「差し替え」が選ばれた場合、6位以降の候補を提示して選び直し。

### 6. Calendar ブロック作成

確認済みのTOP5それぞれに対し:

```
mcp__google-workspace__list_calendars  # 一度だけ
mcp__google-workspace__list_events
  user_google_email: "tsuyoshi.nagamine@efg-technologies.com"
  time_min: "今日 09:00 JST"
  time_max: "今日 19:00 JST"
```

既存予定を取得し、9:00-19:00 の間で **60分の空きスロット** を時系列で見つけて、TOP1から順に埋める。

```
mcp__google-workspace__create_event
  user_google_email: "tsuyoshi.nagamine@efg-technologies.com"
  summary: "[FOCUS #{順位}] {タスクタイトル(40文字以内)}"
  start: "{空きスロット開始}"
  end: "{60分後}"
  description: |
    出典:
    - {URL1}
    - {URL2}

    重み: {合計スコア}
    期限: {due_date or 該当なし}
  timezone: "Asia/Tokyo"
```

空きが5枠ない場合:
- 確保できた件数を報告
- 残りは「翌日に持ち越し候補」として一覧出力(Calendarには入れない)

### 7. サマリ出力

```
## ✓ 本日のフォーカス TOP5 (全件Calendar登録済)

| # | 時間帯 | タスク | 出典 |
|---|--------|--------|------|
| 1 | 09:00-10:00 | xxx | Notion+PR |
| ... |

予備候補(明日繰越):
- yyy
- zzz
```

---

## エッジケース

- **TOP5に満たない**(候補が4件以下): 全件Calendarブロックして、その旨を報告
- **既存予定で9-19時が完全に埋まっている**: ブロック作成は中止し、TOP5を表だけ表示
- **Notion DB取得失敗**: GitHub+Gmailのみで進行(その旨明示)
- **Gmail判定で件数が多い(50件超)**: 件数を表示してユーザに確認(token消費の警告)

## 設計の前提・想定外時の挙動

- 過剰呼び出しを避けるため、Calendar `list_events` は1回だけ取得して内部で空き判定
- 重複統合のしきい値は判定迷ったら **統合せず併記** を優先(誤統合の方がコスト高い)
- 60分単位は固定、`/daily-focus 90min` 等の引数があれば上書き(将来拡張)
- 過去のTOP5履歴は保存しない(都度クリーン抽出)
