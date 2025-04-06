#!/bin/bash
set -euo pipefail # エラー、未定義変数、パイプ失敗で終了

# --- 設定 ---
# 各ファイルのインストール先ディレクトリ
APP_INSTALL_DIR="$HOME/Applications"
ICON_INSTALL_DIR="$HOME/.local/share/icons"
DESKTOP_INSTALL_DIR="$HOME/.local/share/applications"
DEFAULT_CATEGORY="Utility" # カテゴリ引数が省略された場合のデフォルト

# --- ヘルパー関数 ---
log_action() { echo "[INFO] $1..."; }
log_success() { echo "[INFO] $1... Done."; }
log_error() { echo "[ERROR] $1" >&2; exit 1; }

# --- 入力検証 ---
if [ -z "${1:-}" ]; then
  log_error "AppImageのパスが指定されていません。\nUsage: $0 <AppImagePath> [IconPath] [Category]"
fi

APPIMAGE_SRC=$(readlink -f "$1") # 絶対パスを取得
ICON_SRC_REL=${2:-}             # アイコンパス (相対/絶対) or 空
CATEGORY=${3:-$DEFAULT_CATEGORY} # カテゴリ or デフォルト

if [ ! -r "$APPIMAGE_SRC" ]; then
   log_error "AppImageファイルが見つからないか、読み込めません: '$APPIMAGE_SRC'"
fi

# 拡張子チェック (警告のみ)
if [[ ! "$APPIMAGE_SRC" =~ \.[Aa]pp[Ii]mage$ ]]; then
   echo "[WARN] ファイルには標準的な .AppImage 拡張子がありません: '$APPIMAGE_SRC'" >&2
fi

APPIMAGE_FILENAME=$(basename "$APPIMAGE_SRC")
# .AppImage または .appimage を末尾から削除してアプリ名を取得 (大文字小文字無視)
APPNAME=$(basename "$APPIMAGE_SRC" .AppImage | sed 's/\.appimage$//i')

APPIMAGE_DEST="$APP_INSTALL_DIR/$APPIMAGE_FILENAME"
ICON_DEST=""       # アイコンの最終的なパス
ICON_FILENAME=""   # アイコンのファイル名
ICON_ARG=""        # .desktopファイルに書き込むIcon=行

# アイコンが指定されている場合の処理
if [ -n "$ICON_SRC_REL" ]; then
    ICON_SRC=$(readlink -f "$ICON_SRC_REL") # 絶対パスを取得
    if [ ! -r "$ICON_SRC" ]; then
        log_error "アイコンファイルが見つからないか、読み込めません: '$ICON_SRC'"
    fi
    ICON_FILENAME=$(basename "$ICON_SRC")
    ICON_DEST="$ICON_INSTALL_DIR/$ICON_FILENAME"
    ICON_ARG="Icon=$ICON_DEST" # .desktopファイルにはフルパスを指定
fi

DESKTOP_FILE="$DESKTOP_INSTALL_DIR/$APPNAME.desktop"

# --- メイン処理 ---

log_action "必要なディレクトリを作成中"
mkdir -p "$APP_INSTALL_DIR" || log_error "$APP_INSTALL_DIR の作成に失敗しました"
mkdir -p "$ICON_INSTALL_DIR" || log_error "$ICON_INSTALL_DIR の作成に失敗しました"
mkdir -p "$DESKTOP_INSTALL_DIR" || log_error "$DESKTOP_INSTALL_DIR の作成に失敗しました"
log_success "ディレクトリ作成"

log_action "AppImage を $APP_INSTALL_DIR へコピー中"
cp "$APPIMAGE_SRC" "$APPIMAGE_DEST" || log_error "AppImageのコピーに失敗しました"
log_success "AppImage コピー"

log_action "AppImageに実行権限を付与中"
chmod u+x "$APPIMAGE_DEST" || log_error "AppImageへの実行権限付与に失敗しました"
log_success "実行権限付与"

# アイコンが指定されていたらコピー
if [ -n "${ICON_SRC:-}" ]; then
    log_action "アイコンを $ICON_INSTALL_DIR へコピー中"
    cp "$ICON_SRC" "$ICON_DEST" || log_error "アイコンのコピーに失敗しました"
    log_success "アイコンコピー"
fi

log_action ".desktop ファイルを作成中: $DESKTOP_FILE"
# .desktop ファイルを生成
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Name=$APPNAME
Comment=Launcher for $APPNAME AppImage
Exec=env CURSOR_APPIMAGE=1 "$APPIMAGE_DEST" --no-sandbox
Terminal=false
Type=Application
Categories=$CATEGORY
$ICON_ARG
EOF
# cat の終了ステータスを確認 (リダイレクト失敗など)
if [ $? -ne 0 ]; then
  log_error ".desktop ファイルの作成に失敗しました"
fi
# 生成したファイルを検証 (desktop-file-validate があれば)
if command -v desktop-file-validate &> /dev/null; then
  desktop-file-validate "$DESKTOP_FILE" || echo "[WARN] .desktop ファイルの検証で問題が見つかりました: $DESKTOP_FILE" >&2
else
  echo "[INFO] desktop-file-validate コマンドが見つからないため、検証をスキップします"
fi
log_success ".desktop ファイル作成"

log_action "デスクトップデータベースを更新中"
# -q オプションでエラー以外の出力を抑制
update-desktop-database -q "$DESKTOP_INSTALL_DIR" || echo "[WARN] デスクトップデータベースの更新に失敗しました (致命的ではない可能性があります)" >&2
log_success "デスクトップデータベース更新"

# --- 完了メッセージ ---
echo ""
echo "--------------------------------------------------"
echo " AppImage のメニュー統合が完了しました！"
echo "--------------------------------------------------"
echo "  アプリ名:     $APPNAME"
echo "  実行ファイル: $APPIMAGE_DEST"
if [ -n "$ICON_DEST" ]; then
    echo "  アイコン:     $ICON_DEST"
else
    echo "  アイコン:     (指定なし - システムが自動で見つけるかもしれません)"
fi
echo "  .desktop File:$DESKTOP_FILE"
echo "  カテゴリ:     $CATEGORY"
echo ""
echo "アプリケーションメニューから '$APPNAME' を起動できるはずです。"
echo "(変更が完全に反映されるには、ログアウト/再ログインが必要な場合があります)"
echo "--------------------------------------------------"

exit 0
