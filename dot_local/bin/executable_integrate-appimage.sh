#!/bin/bash
set -euo pipefail # エラー、未定義変数、パイプ失敗で終了

# --- 設定 ---
APP_DIR="$HOME/Applications"
EXTRACT_DIR="$APP_DIR/extracted"
ICON_DIR="$HOME/.local/share/icons"
DESKTOP_DIR="$HOME/.local/share/applications"
DEFAULT_CATEGORY="Utility"

# --- ヘルパー関数 ---
log() { echo "[$1] $2${3:+...}"; }
info() { log "INFO" "$1" "${2:-}"; }
success() { log "INFO" "$1 完了" ""; }
error() { log "ERROR" "$1" "" >&2; exit 1; }
warn() { log "WARN" "$1" "" >&2; }

# クリーンアップ関数
cleanup() {
    local exit_code=$?
    [ -n "${TEMP_DIR:-}" ] && [ -d "$TEMP_DIR" ] && rm -rf "$TEMP_DIR"
    # エラーがあった場合のみメッセージ表示 (コード0は成功なのでスキップ)
    if [ $exit_code -ne 0 ]; then
        echo "[ERROR] スクリプトがエラーで終了しました (コード: $exit_code)"
    fi
}
trap cleanup EXIT

# --- 使用方法 ---
usage() {
    cat <<EOF
使用方法: $0 <AppImageパス> [アイコンパス] [カテゴリ] [--extract]
  --extract: AppImageを展開し、展開したAppRunを使用します
EOF
    exit 1
}

# --- 引数解析 ---
EXTRACT_MODE=false
ARGS=()

for arg in "$@"; do
    if [[ "$arg" == "--extract" ]]; then
        EXTRACT_MODE=true
    else
        ARGS+=("$arg")
    fi
done
set -- "${ARGS[@]}"

# --- 入力検証 ---
[[ -z "${1:-}" ]] && error "AppImageのパスが指定されていません。" && usage

APPIMAGE_SRC=$(readlink -f "$1")
ICON_SRC_REL=${2:-}
CATEGORY=${3:-$DEFAULT_CATEGORY}

# 存在チェック
[[ ! -r "$APPIMAGE_SRC" ]] && error "AppImageファイルが見つからないか、読み込めません: '$APPIMAGE_SRC'"

# 拡張子チェック
[[ ! "$APPIMAGE_SRC" =~ \.[Aa]pp[Ii]mage$ ]] && warn "ファイルには標準的な .AppImage 拡張子がありません: '$APPIMAGE_SRC'"

# --- パス設定 ---
APPIMAGE_NAME=$(basename "$APPIMAGE_SRC")
APPNAME=$(basename "$APPIMAGE_SRC" .AppImage | sed 's/\.appimage$//i')
APPIMAGE_DEST="$APP_DIR/$APPIMAGE_NAME"
DESKTOP_FILE="$DESKTOP_DIR/$APPNAME.desktop"
ICON_ARG=""

# 展開モード用の変数設定
if [ "$EXTRACT_MODE" = true ]; then
    EXTRACT_APP_DIR="$EXTRACT_DIR/$APPNAME"
    APPRUN_PATH="$EXTRACT_APP_DIR/AppRun"
fi

# アイコン処理
if [ -n "$ICON_SRC_REL" ]; then
    ICON_SRC=$(readlink -f "$ICON_SRC_REL")
    [[ ! -r "$ICON_SRC" ]] && error "アイコンファイルが見つからないか、読み込めません: '$ICON_SRC'"
    ICON_DEST="$ICON_DIR/$(basename "$ICON_SRC")"
    ICON_ARG="Icon=$ICON_DEST"
fi

# --- メイン処理 ---
# 必要なディレクトリを作成
for dir in "$APP_DIR" "$ICON_DIR" "$DESKTOP_DIR" ${EXTRACT_MODE:+"$EXTRACT_DIR"}; do
    mkdir -p "$dir" || error "${dir##*/} ディレクトリの作成に失敗しました"
done
success "ディレクトリ作成"

# AppImageをコピーして実行権限付与
info "AppImage を $APP_DIR へコピー中"
cp "$APPIMAGE_SRC" "$APPIMAGE_DEST" || error "AppImageのコピーに失敗しました"
chmod u+x "$APPIMAGE_DEST" || error "AppImageへの実行権限付与に失敗しました"
success "AppImage準備"

# 展開処理
if [ "$EXTRACT_MODE" = true ]; then
    info "AppImageを展開中"
    
    # 既存ディレクトリがあれば削除
    [ -d "$EXTRACT_APP_DIR" ] && rm -rf "$EXTRACT_APP_DIR"
    
    # 一時ディレクトリで展開
    TEMP_DIR=$(mktemp -d)
    (cd "$TEMP_DIR" && "$APPIMAGE_DEST" --appimage-extract > /dev/null 2>&1) || 
        error "AppImageの展開に失敗しました"
    
    # squashfs-rootの存在確認
    [ ! -d "$TEMP_DIR/squashfs-root" ] && 
        error "展開に失敗: squashfs-rootディレクトリが見つかりません"
    
    # 展開内容を移動
    mkdir -p "$EXTRACT_APP_DIR"
    cp -a "$TEMP_DIR/squashfs-root/." "$EXTRACT_APP_DIR/" || 
        error "展開ファイルの移動に失敗しました"
    
    # 一時ディレクトリを削除
    rm -rf "$TEMP_DIR"
    
    # AppRunの確認と権限付与
    [ ! -f "$APPRUN_PATH" ] && error "AppRunファイルが見つかりません: $APPRUN_PATH"
    chmod u+x "$APPRUN_PATH" || error "AppRunへの実行権限付与に失敗しました"
    
    success "AppImage展開"
    
    # アイコン自動検出 (ユーザー指定がない場合)
    if [ -z "$ICON_SRC_REL" ]; then
        info "アイコンを自動検出中"
        
        # 検索パスを指定
        ICON_PATHS=(
            # Cursorアプリ固有のパス
            "$EXTRACT_APP_DIR/usr/share/pixmaps/co.anysphere.cursor.png"
            "$EXTRACT_APP_DIR/usr/share/icons/hicolor/512x512/apps/cursor.png"
            "$EXTRACT_APP_DIR/usr/share/icons/hicolor/256x256/apps/cursor.png"
            "$EXTRACT_APP_DIR/usr/share/icons/hicolor/128x128/apps/cursor.png"
            # 一般的なアイコンパス
            "$EXTRACT_APP_DIR/icon.png"
            "$EXTRACT_APP_DIR/icons/icon.png"
            "$EXTRACT_APP_DIR/AppIcon.png"
            # 特定ディレクトリ内の任意のアイコン
            $(ls -1 "$EXTRACT_APP_DIR"/usr/share/icons/hicolor/*/apps/*.png 2>/dev/null || true)
            $(ls -1 "$EXTRACT_APP_DIR"/usr/share/pixmaps/*.png 2>/dev/null || true)
        )
        
        # パスを順に確認
        for icon_path in "${ICON_PATHS[@]}"; do
            if [ -f "$icon_path" ]; then
                ICON_DEST="$ICON_DIR/$(basename "$icon_path")"
                ICON_ARG="Icon=$ICON_DEST"
                
                info "展開ディレクトリからアイコンをコピー中"
                cp "$icon_path" "$ICON_DEST" || warn "アイコンのコピーに失敗しましたが続行します"
                success "アイコンコピー"
                break
            fi
        done
        
        # アイコンが見つからなかった場合
        if [ -z "$ICON_ARG" ]; then
            warn "アイコンが見つかりませんでした。アプリケーション名をアイコン名として使用します"
            ICON_ARG="Icon=$APPNAME"
        fi
    fi
fi

# ユーザー指定アイコンのコピー
if [ -n "$ICON_SRC_REL" ]; then
    info "指定されたアイコンをコピー中"
    cp "$ICON_SRC" "$ICON_DEST" || error "アイコンのコピーに失敗しました"
    success "アイコンコピー"
fi

# .desktopファイル作成
info ".desktopファイルを作成中: $DESKTOP_FILE"

if [ "$EXTRACT_MODE" = true ]; then
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Name=$APPNAME
Comment=Launcher for $APPNAME (extracted AppImage)
Exec=env CURSOR_APPIMAGE=1 ELECTRON_OZONE_PLATFORM_HINT=auto "$APPRUN_PATH" --no-sandbox --enable-features=UseOzonePlatform --ozone-platform=wayland --enable-wayland-ime --wayland-text-input-version=3
Terminal=false
Type=Application
Categories=$CATEGORY
$ICON_ARG
EOF
else
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Name=$APPNAME
Comment=Launcher for $APPNAME AppImage
Exec=env CURSOR_APPIMAGE=1 ELECTRON_OZONE_PLATFORM_HINT=auto "$APPIMAGE_DEST" --no-sandbox --enable-features=UseOzonePlatform --ozone-platform=wayland --enable-wayland-ime --wayland-text-input-version=3
Terminal=false
Type=Application
Categories=$CATEGORY
$ICON_ARG
EOF
fi

# .desktopファイルの検証
command -v desktop-file-validate &> /dev/null && 
    desktop-file-validate "$DESKTOP_FILE" || 
    warn ".desktopファイルの検証でエラーが発生しましたが、影響はない可能性があります"

success ".desktopファイル作成"

# デスクトップデータベース更新
info "デスクトップデータベースを更新中"
update-desktop-database -q "$DESKTOP_DIR" || 
    warn "デスクトップデータベースの更新に失敗しました (致命的ではない可能性があります)"
success "デスクトップデータベース更新"

# --- 完了メッセージ ---
cat <<EOF

--------------------------------------------------
 AppImage のメニュー統合が完了しました！
--------------------------------------------------
  アプリ名:     $APPNAME
  モード:       $([ "$EXTRACT_MODE" = true ] && echo "展開モード (extracted)" || echo "通常モード (AppImage)")
  実行ファイル: $([ "$EXTRACT_MODE" = true ] && echo "$APPRUN_PATH" || echo "$APPIMAGE_DEST")
$([ "$EXTRACT_MODE" = true ] && echo "  展開場所:     $EXTRACT_APP_DIR")
  アイコン:     $([ -n "$ICON_DEST" ] && echo "$ICON_DEST" || echo "(指定なし - システムが自動で見つけるかもしれません)")
  .desktop:    $DESKTOP_FILE
  カテゴリ:     $CATEGORY

アプリケーションメニューから '$APPNAME' を起動できるはずです。
(変更が完全に反映されるには、ログアウト/再ログインが必要な場合があります)
--------------------------------------------------
EOF

exit 0
