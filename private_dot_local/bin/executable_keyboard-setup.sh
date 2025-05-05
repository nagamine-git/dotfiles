#!/bin/bash
set -eu

# --- ヘルパー関数 ---
log() { echo "[$1] $2"; }
info() { log "INFO" "$1"; }
error() { log "ERROR" "$1" >&2; exit 1; }
success() { log "SUCCESS" "$1"; }

show_usage() {
  cat <<EOF
使用方法: $(basename "$0") [オプション]

キーボード設定を適用またはリセットします。

オプション:
  -r, --restart   キーボード設定を完全に再起動します
  -a, --apply     カスタムXKB設定のみを適用します
  -h, --help      このヘルプを表示して終了します

引数がない場合、--applyと同じ動作をします。
EOF
  exit 0
}

# カスタムXKB設定を適用する
apply_custom_xkb() {
  info "カスタムXKB設定を適用しています..."
  
  # カスタム設定ファイルが存在することを確認
  local CUSTOM_XKB_FILE="$HOME/.local/share/xkb/symbols/custom"
  if [ ! -f "$CUSTOM_XKB_FILE" ]; then
    error "カスタムXKBファイルが見つかりません: $CUSTOM_XKB_FILE"
  fi
  
  # 複数のレイヤー設定を適用
  # カスタムXKB記号を設定
  setxkbmap -option -layout "us,jp,custom" -option grp:win_space_toggle
  
  # 完了
  success "カスタムXKB設定が正常に適用されました"
}

# キーボード関連のすべてのサービスを再起動
restart_keyboard_services() {
  info "キーボード関連サービスを再起動しています..."
  
  # fcitx5入力メソッドを再起動
  info "fcitx5を再起動しています..."
  fcitx5 -r -d
  sleep 1
  
  # fusumaジェスチャー認識を再起動
  info "fusumaを再起動しています..."
  systemctl --user restart fusuma
  sleep 1
  
  # カスタムXKB設定を適用
  apply_custom_xkb
  
  success "すべてのキーボード関連サービスが再起動されました"
}

# コマンドライン引数の処理
case "${1:-}" in
  -r|--restart)
    restart_keyboard_services
    ;;
  -a|--apply|"")
    apply_custom_xkb
    ;;
  -h|--help)
    show_usage
    ;;
  *)
    error "不明なオプション: ${1:-}"
    show_usage
    ;;
esac

exit 0 