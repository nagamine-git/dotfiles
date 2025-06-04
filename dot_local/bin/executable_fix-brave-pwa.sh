#!/usr/bin/env bash
#  ===================================================================
#  Brave の PWA 用 .desktop に Wayland フラグ等を自動付与するスクリプト
#  使い方:
#     1) このファイルを ~/.local/bin/fix-brave-pwa に保存し chmod +x
#     2) PWA を新規作成したあと、あるいは定期的に実行する
#        $ fix-brave-pwa
#  ===================================================================

set -euo pipefail

# 追加したいフラグをここで定義
FLAGS='--enable-features=UseOzonePlatform --ozone-platform=wayland --enable-wayland-ime --password-store=basic'

APPS_DIR="$HOME/.local/share/applications"

echo "[*] scanning Brave PWA desktop files …"

find "$APPS_DIR" -name 'brave-*-Default.desktop' -print0 |
while IFS= read -r -d '' file; do
    # 既に --ozone-platform が入っていれば変更しない
    if grep -q -- '--ozone-platform' "$file"; then
        continue
    fi

    echo "    + patching $(basename "$file")"
    sed -i -E "s|^Exec=/opt/brave-bin/brave |Exec=/opt/brave-bin/brave $FLAGS |" "$file"
done

# .desktop キャッシュ更新（メニュー反映を早くするため）
update-desktop-database "$APPS_DIR" &>/dev/null || true
echo "[*] done."
