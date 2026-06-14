---
name: dev-radar
description: neovim/zsh/tmux/claude code 周辺と 1段メタな代替ツールの新動向を WebSearch し、chezmoi 管理下の現環境と照合して取り込み価値を週次で判定するスキャン。「現状維持で十分」結論も尊重する。Use when /dev-radar, 開発環境のアップデート確認, 新ツール調査。
argument-hint: "[--since YYYY-MM-DD] [--detail]"
allowed-tools: Read, Write, Bash, Grep, Glob, WebSearch
---

# dev-radar

前回実行 → 今日の期間で登場した開発環境ツールを検出し、現環境への取り込み価値を判定する。

## 引数
- `--since YYYY-MM-DD`: 期間下限を上書き (省略時は state ファイル or 30 日前)
- `--detail`: 各候補に URL / 既存比較を併記

## 手順

### 1. 期間決定
```bash
STATE=~/.local/state/dev-radar/last_run.json
mkdir -p "$(dirname "$STATE")"
SINCE=$([ -f "$STATE" ] && jq -r .last_run "$STATE" || date -d '30 days ago' +%Y-%m-%d)
TODAY=$(date +%Y-%m-%d)
```

### 2. 環境スキャン
chezmoi 管理下から「使用中ツール一覧」を Grep / Read で抽出:

| ソース | 抽出対象 |
|---|---|
| `~/.local/share/chezmoi/private_dot_config/mise/config.toml` | runtime |
| `~/.local/share/chezmoi/private_dot_config/sheldon/plugins.toml` | zsh plugin |
| `~/.local/share/chezmoi/dot_tmux.conf*` | `set -g @plugin '...'` |
| `~/.local/share/chezmoi/private_dot_config/nvim/init.lua*` | lazy spec (`'owner/repo'`) |
| `~/.local/share/chezmoi/dot_claude/` | agents, skills, settings |
| `~/.local/share/chezmoi/private_dot_config/hypr/` | WM/compositor (Hyprland) 設定・バージョン |
| `pacman -Qqe` (実行) / `/etc/os-release` | システムパッケージ・ディストリ |
| `sw_vers` (darwin) / `uname -sr` | OS 種別・カーネル (Mac か Linux かで判定軸が変わる) |

### 3. WebSearch (カテゴリ別 / 期間内動向)
- 補完エンジン (nvim-cmp / blink.cmp)
- fuzzy finder (telescope / fzf-lua / snacks.picker)
- LSP / formatter (conform / nvim-lint / vim.lsp.config)
- git TUI (lazygit / gitui / jujutsu)
- zsh plugin manager (sheldon 代替)
- tmux / 代替 (zellij)
- エディタ代替 1段メタ (helix / zed)
- dotfiles 管理 1段メタ (home-manager / nix-darwin)
- AI コーディング (claude code / cursor / aider)
- パッケージ管理 1段メタ (nix / mise / homebrew)
- **WM/compositor (Linux)** — Hyprland の動向 + 代替 (niri / river / sway)。スクロール式 (niri) 等のパラダイム変化を見る
- **WM/タイリング (macOS)** — AeroSpace / yabai。Mac で Hyprland 風タイリングを求める場合の選択肢。**現状 macOS ネイティブで足りているなら ⌀**
- **ディストリ/OS-base 2段メタ** — EndeavourOS(Arch) 継続妥当性、immutable 系 (bazzite/Aurora)、Apple Silicon の Asahi Linux。**移行コスト >> 便益が常態なので原則 ⌀、地殻変動時のみ ★**

ソース: GitHub Release / Hacker News / 各 changelog。

> WM/distro は「キャッチアップ」が主目的で「乗り換え」はめったに正解にならない層。
> デファクトの地殻変動 (例: X11→Wayland 級) を**見逃さない**ためにスキャンするのであって、
> 流行ごとに動くためではない。判定は辛口に、「現状維持で十分」を恐れない。

### 4. 判定

| ★ | 意味 |
|---|---|
| ★★★ | 既導入の実質後継・上位互換 (nvim-cmp→blink.cmp 級) |
| ★★ | 同カテゴリ新興、ユーザ環境に直接ヒット |
| ★ | 別カテゴリ・情報として有用 |
| ⌀ | 現状維持で十分 |

機能互換 or 上位互換 + メンテ活発 → ★★★ / 部分代替 → ★★ / それ以外 → ★ or ⌀。

### 5. 出力 (200字想定)

```markdown
## dev-radar (期間 SINCE → TODAY, N日)
検出 M件 / 取込価値 K件

### 推奨アクション (上位3まで)
1. <ツール> ★★★ - <一言根拠> [確認済]
2. <ツール> ★★ - <一言根拠> [推定]

### 結論
- アクションあり: 別議論で <ツール> を検討
- なし: 現状維持で十分
```

`--detail` 時のみ各候補に URL / 既存比較 / 移行コストを追加。

### 6. 状態保存
```bash
jq -n --arg d "$TODAY" '{last_run:$d, deferred:[]}' > "$STATE"
```

`deferred` には「判断保留」を `{tool, decided_at, decision}` で記録。次回スキャンで重複提示を回避する。

## 必須ルール

- **確度併記**: `[確認済]` (release / 公式 announcement) / `[推定]` (HN / 複数ブログ) / `[不明]` (散発情報)
- **煽り禁止**: 革新なしなら「現状維持で十分」を堂々と書く。star 数バズ駆動禁止。ユーザ既存環境との実利で判定
- **alias 提案禁止**: 個人ローカル化で共有性が落ちる
