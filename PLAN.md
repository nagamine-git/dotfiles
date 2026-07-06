# Hyprland 設定: globbing error 修正 + Lua 全面移行

## 背景
- Hyprland 0.55.4 使用中。0.55 で Lua が**正式デフォルト**設定フォーマットになった(`.conf` は従来フォーマットとして動作)。
- `hyprland.conf.tmpl` 15-16行の `source = ~/.config/hypr/monitors.conf` / `workspaces.conf` が**ファイル不在**で globbing error (no match) が出ている。
- 現行 `.tmpl` は529行・chezmoi テンプレート変数(`.theme.colors`/`.theme.fonts`)・GPU 自動検出・ホスト別分岐(`fp7-e14`)を内包し複雑。

## 方針 (ユーザー承認済み)
1. globbing error → `monitors.conf` / `workspaces.conf` を**新規作成**して source を生かす。
2. Lua 全面移行 → `hyprland.lua.tmpl` を新規作成し、`hyprland.conf.tmpl` を置き換える。

## Lua API の主要パターン (v0.55.0 example より検証済み)
- `hl.config({ general={...}, decoration={...}, misc={...}, input={...}, dwindle={...}, master={...}, xwayland={...}, render={...} })`
- `hl.env("KEY","val")`
- `hl.bind(key, dispatcher, opts)` — opts = `{locked=true, repeating=true, mouse=true}` で bindl/bindel/bindm 相当
- `hl.dsp.exec_cmd(cmd)` / `hl.dsp.window.close()` / `hl.dsp.focus({direction=})` / `hl.dsp.window.move({workspace=})` / `hl.dsp.window.float({action="toggle"})` / `hl.dsp.layout("togglesplit")` / `hl.dsp.workspace.toggle_special("magic")` / `hl.dsp.window.fullscreen()` 等
- `hl.window_rule({name=, match={class=, title=, xwayland=, workspace=, float=, fullscreen=}, float=1, no_focus=true, border_color=, suppress_event=, ...})`
- `hl.layer_rule({name=, match={namespace=}, blur=true, ignore_alpha=0.2})`
- `hl.device({name=, sensitivity=})`
- `hl.monitor({output=, mode=, position=, scale=})`
- 色: 文字列 `"rgba(...)"` または `{colors={...}, angle=N}`
- autostart: `hl.on("hyprland.start", function() ... end)` 内で `hl.exec_cmd(...)` を呼ぶ (exec-once 相当)

## 実装手順

### Step 1: globbing error 修正 (monitors.conf / workspaces.conf 作成)
新規ファイル `~/.local/share/chezmoi/private_dot_config/hypr/monitors.conf.tmpl`:
- 中身は lid ハンドラ・VRR コメントと整合する monitor 宣言。
- eDP-1 はホスト別 scale (fp7-e14=1.25 / 他=1)。
- 外部モニタは `monitor=,preferred,auto,1` (auto)。
- テンプレート変数でホスト分岐。

新規 `workspaces.conf.tmpl`:
- scratchpad 用 special workspace ルール (magic/term/notes/desktop) を定義。
- 現行 `.conf` の windowrule で `name:special:*` を参照しているので整合させる。

### Step 2: hyprland.lua.tmpl 作成 (全面移植)
新規 `~/.local/share/chezmoi/private_dot_config/hypr/hyprland.lua.tmpl`:
- 先頭で chezmoi テンプレート変数を取り込み:
  ```lua
  -- chezmoi: template variables {{{
  local colors = { ... }  -- {{ .theme.colors }} を展開
  local fonts = { ... }   -- {{ .theme.fonts }}
  -- }}}
  ```
- 既存 `.tmpl` の全セクションを Lua に変換:
  - GPU 自動検出ロジック (chezmoi `output` で検出済みの `$terminal` を Lua 変数へ注入)
  - autostart (exec-once 全行 → `hl.on("hyprland.start", ...)`)
  - windowrule / layerrule → `hl.window_rule` / `hl.layer_rule`
  - env 全行 → `hl.env`
  - general / decoration / group / animations / dwindle / master / misc / xwayland / render → `hl.config`
  - input / touchpad / device → `hl.config({input=...})` + `hl.device`
  - bind / bindm / bindel / bindl → `hl.bind` (opts で修飾)
  - lid switch (bindl) → `hl.bind("switch:on:Lid Switch", ...)` で dispatch
  - ホスト分岐 (fp7-e14) → chezmoi `{{ if eq .chezmoi.hostname "fp7-e14" }}` で Lua 行を出し分け
- `source =` 行は Lua では不要 (monitors.conf 相当は `hl.monitor()` で直書き)。

### Step 3: 旧ファイル退避 + chezmoi 適用
- `hyprland.conf.tmpl` を削除 (chezmoi で `chezmoi forget` 相当 = ソース側ファイル削除)。
- `chezmoi apply` で `~/.config/hypr/hyprland.lua` 他を生成。

### Step 4: 動作検証 (起動中 Hyprland で)
- `hyprctl reload` で Lua 設定を読み込ませ、parse error がないか確認。
- `hyprctl getoption` / 主要 bind が効くか確認。
- 万一問題あれば `.conf` に即時ロールバック (git で復元)。

## 懸念・リスク
- **autostart (exec-once) の Lua 表現**: example は `hl.on("hyprland.start", ...)` をコメントで示唆するのみ。これが exec-once 相当(起動時1回)か、reload 毎に発火するかが未確定。→ 検証ステップで確認。もし reload 毎発火なら、起動時1回フラグでガードする。
- **`bind` のキー表記**: example は `mainMod.." + Q"` (スペース区切り)。既存 `.conf` の `bind = $mainMod SHIFT CTRL, Return` は `mainMod.." + SHIFT + CTRL + Return"` に変換。
- **`[float; size 30% 40%; center]`**: bind の dispatcher flag。Lua では `hl.dsp.exec_cmd` に埋め込むか、window_rule で代替する要検討。
- **bash スクリプト群** (`hyprctl --batch "..."` 等): Lua でも `hl.dsp.exec_cmd('hyprctl --batch "..."')` でそのまま動く。
- **テーマ色の注入**: chezmoi テンプレートが Lua コードとして valid な文字列を生成するよう、`rgba({{ $c.primary.hex }}cc)` 等を展開。

## 検証後に判断
- autostart の挙動次第でガード有無を決定。
- `[float; size ...]` フラグの扱いを確認して window_rule に落とし込む。
