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
# FLAGS='--enable-features=UseOzonePlatform --ozone-platform=wayland --enable-wayland-ime --wayland-text-input-version=3 --password-store=basic'
FLAGS='--enable-features=UseOzonePlatform --ozone-platform=wayland --gtk-version=4 --enable-wayland-ime  --password-store=basic --disable-background-mode --pwa-flags-conf-debug=1'


APPS_DIR="$HOME/.local/share/applications"

echo "[*] scanning Brave PWA desktop files …"

find "$APPS_DIR" -name 'brave-*-Default.desktop' -print0 |
while IFS= read -r -d '' file; do
    echo "    + patching $(basename "$file")"
    
    # まずExec行を一旦クリーンアップ（基本形に戻す）
    sed -i -E "s|^Exec=/opt/brave-bin/brave .* --profile-directory|Exec=/opt/brave-bin/brave --profile-directory|" "$file"
    
    # 次に新しいフラグを挿入
    sed -i -E "s|^Exec=/opt/brave-bin/brave --profile-directory|Exec=/opt/brave-bin/brave $FLAGS --profile-directory|" "$file"
done

# .desktop キャッシュ更新（メニュー反映を早くするため）
update-desktop-database "$APPS_DIR" &>/dev/null || true
echo "[*] done."
