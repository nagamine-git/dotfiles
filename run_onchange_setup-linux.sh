#!/bin/bash

set -eu # エラー時や未定義変数使用時にスクリプトを終了させる

SOURCE_DIR='/home/tsuyoshi/.local/share/chezmoi'
PACKAGE_LIST_FILE="$SOURCE_DIR/private_dot_config/chezmoi/apt-packages.txt"

# パッケージリストが存在するか確認
if [ ! -f "$PACKAGE_LIST_FILE" ]; then
  echo "Error: Package list file not found at $PACKAGE_LIST_FILE"
  exit 1
fi

echo "Updating package lists..."
# apt update を実行 (sudoが必要)
sudo apt update

echo "Installing packages listed in $PACKAGE_LIST_FILE..."
grep -v '^#' "$PACKAGE_LIST_FILE" | grep -v '^\s*$' | xargs sudo apt install -y

echo "apt package installation process finished."

# 必要であれば、古いパッケージの削除なども追加できる
echo "Running apt autoremove..."
sudo apt autoremove -y
 echo "Running apt clean..."
sudo apt clean

# zsh 
chsh -s /bin/zsh

# mise
curl https://mise.run | sh

mise i

mkdir -p ~/Pictures/Wallpapers && wget --content-disposition -P ~/Pictures/Wallpapers "https://unsplash.com/photos/phIFdC6lA4E/download?ixid=M3wxMjA3fDB8MXxhbGx8fHx8fHx8fHwxNzQzODUwMjgyfA&force=true"

TMPDIR=$(mktemp -d) && wget -q -O - "https://master.dl.sourceforge.net/project/arc-xfwm4-hidpi/arc-theme-xfwm4-hidpi.tar.gz?viasf=1" | tar -xz -C "$TMPDIR" && mkdir -p ~/.themes && mv "$TMPDIR"/Arc* ~/.themes/ && rm -rf "$TMPDIR" && echo "Arc HiDPI themes installed into ~/.themes/"

curl -fsS https://dl.brave.com/install.sh | sh

# フォント設定
mkdir -p ~/.local/share/fonts

# Firgeフォントのインストール
if [ ! -f ~/.local/share/fonts/Firge35Nerd-Console-Regular.ttf ]; then
    echo "Firgeフォントをインストールしています..."

    # Firge35Nerd Consoleをダウンロード
    FIRGE_VERSION="0.2.0"
    FIRGE_URL="https://github.com/yuru7/Firge/releases/download/v${FIRGE_VERSION}/FirgeNerd_v${FIRGE_VERSION}.zip"
    wget -O /tmp/firge.zip "$FIRGE_URL"

    # 解凍して配置
    mkdir -p /tmp/firge
    unzip -o /tmp/firge.zip -d /tmp/firge
    cp /tmp/firge/FirgeNerd_v${FIRGE_VERSION}/*.ttf ~/.local/share/fonts/

    # 片付け
    rm -rf /tmp/firge /tmp/firge.zip
fi

# RobotoNotoSansJPフォントのインストール
if [ ! -f ~/.local/share/fonts/Roboto-NotoSansJP-Regular.ttf ]; then
    echo "RobotoNotoSansJPフォントをインストールしています..."

    # 既存のディレクトリがあれば削除
    if [ -d /tmp/robotonoto ]; then
        rm -rf /tmp/robotonoto
    fi

    # リポジトリをクローンして必要なファイルをコピー
    git clone --depth 1 https://github.com/reindex-ot/RobotoNotoSansJP.git /tmp/robotonoto
    cp /tmp/robotonoto/*.ttf ~/.local/share/fonts/

    # 片付け
    rm -rf /tmp/robotonoto
fi

# フォントキャッシュの更新
fc-cache -f -v


if ! command -v starship &> /dev/null; then
    curl -sS https://starship.rs/install.sh | sh
fi

if ! command -v sheldon &> /dev/null; then
    curl --proto '=https' -fLsS https://rossmacarthur.github.io/install/crate.sh \
        | bash -s -- --repo rossmacarthur/sheldon --to ~/.local/bin
fi

curl -LO https://github.com/neovim/neovim/releases/latest/download/nvim-linux-x86_64.tar.gz && mkdir -p ~/.local/share && tar -xzf nvim-linux-x86_64.tar.gz -C ~/.local/share/ && echo 'export PATH="$HOME/.local/share/nvim-linux-x86_64/bin:$PATH"' >> ~/.zshrc && rm nvim-linux-x86_64.tar.gz && echo "Neovim installed to ~/.local/share/, PATH added to ~/.zshrc. Run 'source ~/.zshrc' or open a new Zsh terminal to use the 'nvim' command."


