# シンプルクロスプラットフォーム対応dotfiles

このリポジトリは、Mac/Linuxで共通して使える最小限の開発環境セットアップのためのdotfilesです。  
[chezmoi](https://www.chezmoi.io/)を使用して、複数の環境間で一貫した設定を維持します。

## クイックセットアップ

### 1. chezmoiをインストール

```bash
sh -c "$(curl -fsLS get.chezmoi.io)" -- -b $HOME/.local/bin
export PATH="$HOME/.local/bin:$PATH"
```

### 2. dotfilesを初期化して適用

```bash
# dotfilesを初期化
chezmoi init https://github.com/nagamine-git/dotfiles.git

# 変更内容をプレビュー
chezmoi diff

# dotfilesを適用
chezmoi apply -v
```

### 3. 環境固有のセットアップを実行

```bash
# MacOS固有のセットアップ
chezmoi execute-template < ~/.local/share/chezmoi/.chezmoitemplates/darwin.tmpl | bash

# もしくはLinux固有のセットアップ
chezmoi execute-template < ~/.local/share/chezmoi/.chezmoitemplates/linux.tmpl | bash
```

## 詳細セットアップガイド

### MacOS環境

1. **基本ツールのインストール**
   - Homebrew経由でgit, tmux, neovim, fzfなどがインストールされます
   - 日本語対応フォント（Firge, RobotoNotoSansJP）が自動的にインストールされます

2. **キーボードカスタマイズ (Karabiner)**
   - 親指センサー機能（ThumbSense）でマウスレス操作
   - Alt+hjklでVimスタイルのカーソル移動

3. **ターミナル設定**
   - AlacrittyでFirge35Nerd Consoleフォントを設定
   - Starshipプロンプトが自動的に設定されます

### Linux環境（Debian/Ubuntu）

1. **基本ツールとテーマ**
   - 基本パッケージと日本語入力（ibus-mozc）がインストールされます
   - Arc Theme、Papirus Icon、高品質フォントが自動的にインストールされます

2. **キーボードカスタマイズ (XKB)**
   - CapsLockとCtrlの入れ替え
   - Alt+hjklでVimスタイルのナビゲーション
   - 自動起動時に設定が適用されます

3. **Fusumaタッチパッドジェスチャー**
   - MacのTrackpadジェスチャーに似た操作を実現
   - マルチタッチジェスチャーでウィンドウ操作やワークスペース切り替え
   - Systemdサービスとして自動起動

4. **UI設定**
   - GTK設定でArc-Darkテーマ、Papirus-Darkアイコン、Alacrittyの設定が適用されます
   - 推奨壁紙: [雪山と星空の風景](https://unsplash.com/photos/snow-mountain-under-stars-phIFdC6lA4E)

## 日常的な操作

```bash
# 最新の設定を取得して適用
chezmoi update

# 設定ディレクトリを開く
chezmoi cd

# 特定のファイルを編集
chezmoi edit ~/.zshrc

# 変更をプレビュー/適用
chezmoi diff
chezmoi apply

# dotfilesの状態確認
chezmoi status

# 設定ファイルの追加
chezmoi add ~/.config/newapp/config.yaml
```

## 使用環境とコンポーネント

### 共通コア設定
- **シェル環境**: zsh + Oh-My-Zsh + Starship
- **開発ツール**: git, tmux, neovim
- **Starship**: `~/.config/starship.toml`で設定可能な高速プロンプト ([公式ドキュメント](https://starship.rs/config/))

### 高品質フォント
- **Firge35Nerd Console**: プログラミング用日本語フォント（Fira Code + 源ノ角ゴシック）
- **RobotoNotoSansJP**: 日本語とラテン文字の調和を実現するハイブリッドフォント

### デスクトップ環境（Linux）
- **Arc Theme**: 洗練されたGTK/GNOMEテーマ（ダーク/ライト両対応）
- **Papirus Icon**: SVGベースの高品質アイコンセット

## ディレクトリ構造

```
dotfiles/
├── .chezmoitemplates/      # 環境別セットアップスクリプト
├── bin_linux/              # Linuxのみのスクリプト
├── dot_config/             # 各種設定ファイル
│   ├── nvim/               # Neovim設定
│   ├── git/                # Git設定
│   ├── starship/           # Starship設定
│   ├── fusuma/             # タッチパッド設定（Linux）
│   ├── autostart_linux/    # 自動起動設定（Linux）
│   └── systemd_linux/      # Systemdサービス設定（Linux）
├── dot_local_share_linux/  # カスタムキーボード設定（Linux）
└── その他の設定ファイル（dotfiles）
```