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
AppImage管理ツール - インストールとアンインストールを行います

使用方法: 
  インストール: $0 install <AppImageパス> [アイコンパス] [カテゴリ] [--extract]
  アンインストール: $0 uninstall [アプリ名]

オプション:
  --extract: AppImageを展開し、展開したAppRunを使用します
EOF
    exit 1
}

# --- インストール関連機能 ---
do_install() {
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
Exec=env CURSOR_APPIMAGE=1 "$APPRUN_PATH" --no-sandbox
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
Exec=env CURSOR_APPIMAGE=1 "$APPIMAGE_DEST" --no-sandbox
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
}

# --- アンインストール関連機能 ---
# 必要なディレクトリの確認
check_directories() {
    local missing=false
    for dir in "$APP_DIR" "$EXTRACT_DIR" "$DESKTOP_DIR" "$ICON_DIR"; do
        if [ ! -d "$dir" ]; then
            warn "ディレクトリが存在しません: $dir"
            missing=true
        fi
    done
    
    if [ "$missing" = true ]; then
        warn "一部のディレクトリが見つかりません。AppImageがインストールされていない可能性があります。"
    fi
}

# 展開済みAppImageの一覧取得
get_extracted_apps() {
    local apps=()
    if [ -d "$EXTRACT_DIR" ]; then
        for app_dir in "$EXTRACT_DIR"/*; do
            if [ -d "$app_dir" ] && [ -f "$app_dir/AppRun" ]; then
                app_name=$(basename "$app_dir")
                apps+=("extracted:$app_name")
            fi
        done
    fi
    echo "${apps[@]:-}"
}

# 非展開AppImageの一覧取得
get_normal_apps() {
    local apps=()
    if [ -d "$APP_DIR" ]; then
        # ワイルドカードのマッチングを改善
        shopt -s nullglob # マッチするファイルがない場合は空のリストを返す
        local app_files=("$APP_DIR"/*.AppImage "$APP_DIR"/*.appimage)
        shopt -u nullglob
        
        for app_file in "${app_files[@]}"; do
            if [ -f "$app_file" ] && [ -x "$app_file" ]; then
                app_name=$(basename "$app_file" | sed -E 's/\.(AppImage|appimage)$//')
                
                # 展開済みAppImageと重複しないか確認
                if [ ! -d "$EXTRACT_DIR/$app_name" ]; then
                    apps+=("normal:$app_name")
                fi
            fi
        done
    fi
    echo "${apps[@]:-}"
}

# デスクトップファイルの削除
remove_desktop_file() {
    local app_name="$1"
    local desktop_file="$DESKTOP_DIR/$app_name.desktop"
    
    if [ -f "$desktop_file" ]; then
        info "$app_name の.desktopファイルを削除中"
        rm -f "$desktop_file" || warn ".desktopファイルの削除に失敗しました: $desktop_file"
        success ".desktopファイル削除"
    fi
}

# アイコンの検索と削除
remove_icon() {
    local app_name="$1"
    
    # desktopファイルからアイコンを特定
    local desktop_file="$DESKTOP_DIR/$app_name.desktop"
    local icon_path=""
    
    if [ -f "$desktop_file" ]; then
        icon_path=$(grep -o 'Icon=.*' "$desktop_file" | cut -d'=' -f2)
    fi
    
    # アイコンが見つかった場合は削除
    if [ -n "$icon_path" ] && [ -f "$icon_path" ]; then
        info "アイコンを削除中: $icon_path"
        rm -f "$icon_path" || warn "アイコンの削除に失敗しました: $icon_path"
        success "アイコン削除"
    elif [ -n "$icon_path" ] && [[ "$icon_path" != /* ]]; then
        # 絶対パスでない場合は、アイコンディレクトリ内を検索
        for icon_file in "$ICON_DIR"/$app_name.* "$ICON_DIR"/$app_name; do
            if [ -f "$icon_file" ]; then
                info "アイコンを削除中: $icon_file"
                rm -f "$icon_file" || warn "アイコンの削除に失敗しました: $icon_file"
                success "アイコン削除"
            fi
        done
    else
        info "アイコンが見つからないか、削除する必要がありません"
    fi
}

# 展開済みAppImageのアンインストール
uninstall_extracted_app() {
    local app_name="$1"
    local app_dir="$EXTRACT_DIR/$app_name"
    
    # 展開ディレクトリの削除
    if [ -d "$app_dir" ]; then
        info "展開ディレクトリを削除中: $app_dir"
        rm -rf "$app_dir" || warn "展開ディレクトリの削除に失敗しました: $app_dir"
        success "展開ディレクトリ削除"
    fi
    
    # デスクトップファイルの削除
    remove_desktop_file "$app_name"
    
    # アイコンの削除
    remove_icon "$app_name"
    
    echo "$app_name (展開済み) がアンインストールされました"
}

# 非展開AppImageのアンインストール
uninstall_normal_app() {
    local app_name="$1"
    local app_file="$APP_DIR/$app_name.AppImage"
    
    # 大文字小文字を区別せずに検索
    if [ ! -f "$app_file" ]; then
        app_file="$APP_DIR/$app_name.appimage"
        if [ ! -f "$app_file" ]; then
            # ワイルドカードのマッチングを改善
            shopt -s nullglob
            local app_files=("$APP_DIR"/*.AppImage "$APP_DIR"/*.appimage)
            shopt -u nullglob
            
            for f in "${app_files[@]}"; do
                if [[ "$(basename "$f" | sed -E 's/\.(AppImage|appimage)$//')" == "$app_name" ]]; then
                    app_file="$f"
                    break
                fi
            done
        fi
    fi
    
    # AppImageファイルの削除
    if [ -f "$app_file" ]; then
        info "AppImageファイルを削除中: $app_file"
        rm -f "$app_file" || warn "AppImageファイルの削除に失敗しました: $app_file"
        success "AppImageファイル削除"
    else
        warn "AppImageファイルが見つかりません: $app_name"
    fi
    
    # デスクトップファイルの削除
    remove_desktop_file "$app_name"
    
    # アイコンの削除
    remove_icon "$app_name"
    
    echo "$app_name がアンインストールされました"
}

# アンインストール実行
perform_uninstall() {
    local app_type="$1"
    local app_name="$2"
    
    if [ "$app_type" = "extracted" ]; then
        uninstall_extracted_app "$app_name"
    else
        uninstall_normal_app "$app_name"
    fi
    
    # デスクトップデータベースの更新
    if command -v update-desktop-database &> /dev/null; then
        info "デスクトップデータベースを更新中"
        update-desktop-database -q "$DESKTOP_DIR" || 
            warn "デスクトップデータベースの更新に失敗しました"
        success "デスクトップデータベース更新"
    fi
}

# アンインストールメイン処理
do_uninstall() {
    local app_name="${1:-}"
    
    # ディレクトリ確認
    check_directories
    
    # AppImage一覧取得
    local extracted_apps=($(get_extracted_apps))
    local normal_apps=($(get_normal_apps))
    
    # インストール済みチェック
    if [ ${#extracted_apps[@]} -eq 0 ] && [ ${#normal_apps[@]} -eq 0 ]; then
        error "インストールされているAppImageが見つかりません"
    fi
    
    # 特定のアプリ名が指定された場合
    if [ -n "$app_name" ]; then
        local found=false
        
        # 展開済みAppImageから検索
        for app in "${extracted_apps[@]}"; do
            if [ "${app#extracted:}" = "$app_name" ]; then
                perform_uninstall "extracted" "$app_name"
                found=true
                break
            fi
        done
        
        # 非展開AppImageから検索 (まだ見つかっていない場合)
        if [ "$found" = false ]; then
            for app in "${normal_apps[@]}"; do
                if [ "${app#normal:}" = "$app_name" ]; then
                    perform_uninstall "normal" "$app_name"
                    found=true
                    break
                fi
            done
        fi
        
        # 見つからなかった場合はエラー
        if [ "$found" = false ]; then
            error "指定されたアプリが見つかりません: $app_name"
        fi
        
        exit 0
    fi
    
    # アプリ一覧表示
    echo "アンインストール可能なAppImageアプリ:"
    echo "--------------------------------------------------"
    
    local app_count=0
    
    # 展開済みAppImage表示
    if [ ${#extracted_apps[@]} -gt 0 ]; then
        echo "【展開済みAppImage】"
        for app in "${extracted_apps[@]}"; do
            app_count=$((app_count+1))
            app_name="${app#extracted:}"
            echo "$app_count) $app_name (展開済み)"
        done
        echo ""
    fi
    
    # 非展開AppImage表示
    if [ ${#normal_apps[@]} -gt 0 ]; then
        echo "【通常AppImage】"
        for app in "${normal_apps[@]}"; do
            app_count=$((app_count+1))
            app_name="${app#normal:}"
            echo "$app_count) $app_name"
        done
        echo ""
    fi
    
    echo "--------------------------------------------------"
    
    # アプリ選択
    local selection
    read -p "アンインストールするアプリの番号を入力 (1-$app_count): " selection
    
    if ! [[ "$selection" =~ ^[0-9]+$ ]] || [ "$selection" -lt 1 ] || [ "$selection" -gt $app_count ]; then
        error "無効な選択です: $selection"
    fi
    
    local selected_app=""
    local selected_type=""
    local current=0
    
    # 選択されたアプリを特定
    for app in "${extracted_apps[@]}" "${normal_apps[@]}"; do
        current=$((current+1))
        if [ $current -eq $selection ]; then
            if [[ "$app" == extracted:* ]]; then
                selected_type="extracted"
                selected_app="${app#extracted:}"
            else
                selected_type="normal"
                selected_app="${app#normal:}"
            fi
            break
        fi
    done
    
    # 選択確認
    read -p "$selected_app をアンインストールします。よろしいですか？ (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "アンインストールをキャンセルしました。"
        exit 0
    fi
    
    # アンインストール実行
    perform_uninstall "$selected_type" "$selected_app"
}

# --- メイン処理 ---
main() {
    # コマンド引数がない場合
    if [ $# -eq 0 ]; then
        usage
        exit 1
    fi
    
    # コマンド解析
    case "$1" in
        install)
            shift
            do_install "$@"
            ;;
        uninstall)
            shift
            do_uninstall "$@"
            ;;
        *)
            # 互換性のために「install」を省略可能に
            if [[ "$1" == *.AppImage ]] || [[ "$1" == *.appimage ]]; then
                do_install "$@"
            else
                error "無効なコマンドです: $1"
                usage
            fi
            ;;
    esac
}

main "$@" 