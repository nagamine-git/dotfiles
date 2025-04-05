#!/bin/sh
# ~/.local/share/chezmoi/run_onchange_install-apt-packages.sh

set -eu # エラー時や未定義変数使用時にスクリプトを終了させる

# chezmoi 管理下のパッケージリストファイルのパスを取得
# chezmoi source-path コマンドでソースディレクトリ内のファイルの絶対パスを取得できる
PACKAGE_LIST_FILE=$(chezmoi source-path private_dot_config/chezmoi/apt-packages.txt)

# パッケージリストが存在するか確認
if [ ! -f "$PACKAGE_LIST_FILE" ]; then
  echo "Error: Package list file not found at $PACKAGE_LIST_FILE"
  exit 1
fi

echo "Updating package lists..."
# apt update を実行 (sudoが必要)
sudo apt update

echo "Installing packages listed in $PACKAGE_LIST_FILE..."
# xargs を使ってファイルの内容を引数として apt install に渡す
# grep -v '^#' でコメント行を除外
# grep -v '^\s*$' で空行を除外
grep -v '^#' "$PACKAGE_LIST_FILE" | grep -v '^\s*$' | xargs sudo apt install -y

echo "apt package installation process finished."

# 必要であれば、古いパッケージの削除なども追加できる
# echo "Running apt autoremove..."
# sudo apt autoremove -y
# echo "Running apt clean..."
# sudo apt clean
