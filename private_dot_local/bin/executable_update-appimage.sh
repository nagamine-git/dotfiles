#!/bin/bash
set -euo pipefail

# --- 設定 ---
APP_DIR="$HOME/Applications"
EXTRACT_DIR="$APP_DIR/extracted"
TEMP_DIR=""
DOWNLOAD_DIR="$HOME/Downloads/AppImages"
INTEGRATE_SCRIPT="$HOME/.local/bin/integrate-appimage.sh"

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
    if [ $exit_code -ne 0 ]; then
        echo "[ERROR] スクリプトがエラーで終了しました (コード: $exit_code)"
    fi
}
trap cleanup EXIT

# ディレクトリ確認と作成
check_directories() {
    for dir in "$APP_DIR" "$EXTRACT_DIR" "$DOWNLOAD_DIR"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir" || error "ディレクトリ作成に失敗: $dir"
        fi
    done
}

# インストール済みAppImage一覧取得
get_installed_apps() {
    local apps=()
    # 展開されているAppImageを検索
    if [ -d "$EXTRACT_DIR" ]; then
        for app_dir in "$EXTRACT_DIR"/*; do
            if [ -d "$app_dir" ] && [ -f "$app_dir/AppRun" ]; then
                app_name=$(basename "$app_dir")
                apps+=("$app_name")
            fi
        done
    fi
    
    # 空の配列の場合はエラー
    if [ ${#apps[@]} -eq 0 ]; then
        return 1
    fi
    
    # 配列の各要素をスペース区切りで出力
    echo "${apps[@]}"
}

# 対話的にGitHubリポジトリを入力
prompt_github_repo() {
    local app_name="$1"
    local default_repo=""
    
    # アプリ名からデフォルトのリポジトリを推測
    case "$app_name" in
        cursor|Cursor*)
            default_repo="cursor-engineering/cursor"
            ;;
        obsidian|Obsidian*)
            default_repo="obsidianmd/obsidian-releases"
            ;;
        onlyoffice|OnlyOffice*)
            default_repo="ONLYOFFICE/DesktopEditors"
            ;;
        bitwarden|Bitwarden*)
            default_repo="bitwarden/clients"
            ;;
        cider|Cider*)
            default_repo="ciderapp/Cider"
            ;;
    esac
    
    echo "AppImageの取得方法を選択してください:"
    echo "1. GitHubリポジトリから最新版を自動取得"
    echo "2. ダウンロードURLを直接指定"
    read -p "選択 (1/2): " dl_method
    
    if [ "$dl_method" = "2" ]; then
        read -p "AppImageのダウンロードURLを入力: " download_url
        if [ -z "$download_url" ] || [[ ! "$download_url" =~ \.[Aa]pp[Ii]mage$ ]]; then
            error "有効なAppImageのURLではありません"
        fi
        echo "URL:$download_url"
        return 0
    fi
    
    local prompt="GitHubリポジトリを入力 (例: owner/repo)"
    if [ -n "$default_repo" ]; then
        prompt="$prompt [$default_repo]"
    fi
    
    read -p "$prompt: " repo
    
    if [ -z "$repo" ] && [ -n "$default_repo" ]; then
        repo="$default_repo"
    fi
    
    if [ -z "$repo" ] || [[ ! "$repo" =~ ^[^/]+/[^/]+$ ]]; then
        error "有効なリポジトリ形式ではありません (owner/repo形式で入力してください)"
    fi
    
    echo "$repo"
}

# GitHubのリリースURLからAppImageをダウンロード
download_from_github() {
    local repo_or_url="$1"
    local app_name="$2"
    
    # URLかリポジトリか判定
    if [[ "$repo_or_url" == URL:* ]]; then
        local download_url="${repo_or_url#URL:}"
        local file_name=$(basename "$download_url")
        local download_path="$DOWNLOAD_DIR/$file_name"
        
        info "指定されたURLからダウンロード中: $file_name"
        if ! curl -L -o "$download_path" "$download_url"; then
            error "ダウンロードに失敗しました"
        fi
        
        chmod +x "$download_path"
        success "ダウンロード"
        
        echo "$download_path"
        return 0
    fi
    
    # 以下、GitHubリポジトリからのダウンロード
    local repo="$repo_or_url"
    info "GitHubからの最新リリース情報を取得中: $repo"
    
    # API経由で最新リリース情報を取得
    TEMP_DIR=$(mktemp -d)
    local release_json="$TEMP_DIR/release.json"
    
    if ! curl -s -L "https://api.github.com/repos/$repo/releases/latest" -o "$release_json"; then
        error "GitHubからの情報取得に失敗しました"
    fi
    
    # AppImageアセットを探す
    local download_url=$(grep -o '"browser_download_url": ".*\.AppImage"' "$release_json" | head -1 | cut -d'"' -f4)
    
    if [ -z "$download_url" ]; then
        error "AppImageファイルが見つかりませんでした"
    fi
    
    local file_name=$(basename "$download_url")
    local download_path="$DOWNLOAD_DIR/$file_name"
    
    info "ダウンロード中: $file_name"
    if ! curl -L -o "$download_path" "$download_url"; then
        error "ダウンロードに失敗しました"
    fi
    
    chmod +x "$download_path"
    success "ダウンロード"
    
    echo "$download_path"
}

# アプリの更新
update_app() {
    local app_name="$1"
    local app_dir="$EXTRACT_DIR/$app_name"
    
    if [ ! -d "$app_dir" ]; then
        error "アプリディレクトリが見つかりません: $app_dir"
    fi
    
    # GitHubリポジトリの入力
    local repo=$(prompt_github_repo "$app_name")
    
    # 最新AppImageのダウンロード
    local appimage_path=$(download_from_github "$repo" "$app_name")
    
    # 現在のAppRunのバックアップを取る
    local backup_dir="$app_dir.bak.$(date +%Y%m%d%H%M%S)"
    info "バックアップ作成中: $backup_dir"
    cp -a "$app_dir" "$backup_dir" || error "バックアップの作成に失敗しました"
    success "バックアップ作成"
    
    # 古いディレクトリを削除
    rm -rf "$app_dir" || error "古いアプリケーションデータの削除に失敗しました"
    
    # 新しいAppImageを展開
    info "AppImageを統合・展開中"
    if ! "$INTEGRATE_SCRIPT" "$appimage_path" "" "" --extract; then
        warn "統合に失敗しました。バックアップから復元します。"
        rm -rf "$app_dir" 2>/dev/null || true
        mv "$backup_dir" "$app_dir"
        error "AppImageの統合に失敗しました"
    fi
    
    success "アプリケーション $app_name の更新"
    
    # 成功したらバックアップを削除するか確認
    read -p "バックアップを削除しますか？ (y/N): " delete_backup
    if [[ "$delete_backup" =~ ^[Yy]$ ]]; then
        rm -rf "$backup_dir" && success "バックアップ削除" || warn "バックアップの削除に失敗しました"
    else
        echo "バックアップを保持: $backup_dir"
    fi
}

# --- メイン処理 ---
main() {
    # 依存関係の確認
    if [ ! -f "$INTEGRATE_SCRIPT" ]; then
        error "integrate-appimage.sh スクリプトが見つかりません: $INTEGRATE_SCRIPT"
    fi
    
    # 必要なディレクトリの確認
    check_directories
    
    # インストール済みアプリ一覧を取得して表示
    local app_str=$(get_installed_apps) || error "展開されたAppImageアプリが見つかりません"
    local apps=($app_str)
    local app_count=${#apps[@]}
    
    echo "更新可能なAppImageアプリ:"
    for i in "${!apps[@]}"; do
        echo "$((i+1)). ${apps[$i]}"
    done
    echo ""
    
    # アプリ選択
    local selection
    read -p "更新するアプリの番号を入力 (1-$app_count): " selection
    
    if ! [[ "$selection" =~ ^[0-9]+$ ]] || [ "$selection" -lt 1 ] || [ "$selection" -gt $app_count ]; then
        error "無効な選択番号です: $selection (1-$app_count の範囲で入力してください)"
    fi
    
    local selected_app="${apps[$((selection-1))]}"
    
    # 選択されたアプリの更新
    update_app "$selected_app"
    
    echo ""
    echo "--------------------------------------------------"
    echo " AppImage の更新が完了しました！"
    echo "--------------------------------------------------"
    echo "  アプリ名: $selected_app"
    echo "  場所: $EXTRACT_DIR/$selected_app"
    echo "--------------------------------------------------"
}

main "$@" 