#!/bin/bash
set -euo pipefail

# --- 設定 ---
APP_DIR="$HOME/Applications"
EXTRACT_DIR="$APP_DIR/extracted"
ICON_DIR="$HOME/.local/share/icons"
DESKTOP_DIR="$HOME/.local/share/applications"

# --- ヘルパー関数 ---
log() { echo "[$1] $2${3:+...}"; }
info() { log "INFO" "$1" "${2:-}"; }
success() { log "INFO" "$1 完了" ""; }
error() { log "ERROR" "$1" "" >&2; exit 1; }
warn() { log "WARN" "$1" "" >&2; }

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

# メインメニュー
main() {
    # ディレクトリ確認
    check_directories
    
    # AppImage一覧取得
    local extracted_apps=($(get_extracted_apps))
    local normal_apps=($(get_normal_apps))
    
    # インストール済みチェック
    if [ ${#extracted_apps[@]} -eq 0 ] && [ ${#normal_apps[@]} -eq 0 ]; then
        error "インストールされているAppImageが見つかりません"
    fi
    
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
            selected_app="$app"
            break
        fi
    done
    
    if [[ "$selected_app" == extracted:* ]]; then
        selected_type="extracted"
        selected_app="${selected_app#extracted:}"
    else
        selected_type="normal"
        selected_app="${selected_app#normal:}"
    fi
    
    # 確認
    local app_desc="$selected_app $([ "$selected_type" = "extracted" ] && echo "(展開済み)" || echo "")"
    read -p "本当に「$app_desc」をアンインストールしますか？ (y/N): " confirm
    
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "アンインストールをキャンセルしました"
        exit 0
    fi
    
    # アンインストール実行
    perform_uninstall "$selected_type" "$selected_app"
    
    echo ""
    echo "--------------------------------------------------"
    echo " AppImage のアンインストールが完了しました！"
    echo "--------------------------------------------------"
    echo "  アプリ名: $app_desc"
    echo "--------------------------------------------------"
}

main "$@" 