#!/bin/bash

set -eu # エラー時や未定義変数使用時にスクリプトを終了させる

SOURCE_DIR='/home/tsuyoshi/.local/share/chezmoi'
PACKAGE_LIST_FILE="$SOURCE_DIR/private_dot_config/chezmoi/apt-packages.txt"

# 汎用インストール関数
install_if_missing() {
  local cmd=$1
  local name=${2:-$1}
  local install_cmd=$3

  if ! command -v "$cmd" &> /dev/null; then
    echo "Installing $name..."
    eval "$install_cmd"
  else
    echo "$name already installed, skipping"
  fi
}

# パッケージリストが存在するか確認
if [ ! -f "$PACKAGE_LIST_FILE" ]; then
  echo "Error: Package list file not found at $PACKAGE_LIST_FILE"
  exit 1
fi

# パッケージマネージャの更新
echo "Updating package lists..."
sudo apt update

# aptパッケージのインストール
echo "Installing packages listed in $PACKAGE_LIST_FILE..."
while read -r package; do
  [[ "$package" =~ ^#.*$ || -z "$package" ]] && continue
  
  if ! dpkg -l | grep -q "^ii  $package "; then
    sudo apt install -y "$package"
    echo "Installed $package"
  else
    echo "Package $package already installed, skipping"
  fi
done < <(grep -v '^#' "$PACKAGE_LIST_FILE" | grep -v '^\s*$')

# クリーンアップ
echo "apt package installation process finished."
echo "Running apt autoremove & clean..."
sudo apt autoremove -y && sudo apt clean

# snapdのインストール
install_if_missing snapd snapd "sudo snap install snapd"

# Snap applications in Xfce menu
echo "Setting up Snap applications in Xfce menu..."
if [ -d "/var/lib/snapd/desktop/applications" ]; then
    sudo find /usr/share/applications -xtype l -delete
    sudo ln -sf /var/lib/snapd/desktop/applications/*.desktop /usr/share/applications/
    echo "Snap applications added to Xfce menu"
else
    echo "Snap applications directory not found, skipping menu setup"
fi

# zshへの変更
[ "$SHELL" != "/bin/zsh" ] && { echo "Changing shell to zsh..."; chsh -s /bin/zsh; } || echo "Shell already set to zsh, skipping"

# mise
install_if_missing mise mise "curl https://mise.run | sh && mise i"

# GitHub CLI
install_if_missing gh "GitHub CLI" "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && sudo apt update && sudo apt install gh -y"

# GitHub認証
gh auth status || gh auth login

# cargo
cargo install sheldon eza

# ghq
install_if_missing ghq ghq "go install github.com/x-motemen/ghq@latest"

# gh-q拡張機能
if ! gh extension list | grep -q "kawarimidoll/gh-q"; then
    echo "Installing gh-q extension..."
    gh extension install kawarimidoll/gh-q
else
    echo "gh-q extension already installed, skipping"
fi

# Wallpaper
WALLPAPER_FILE="$HOME/Pictures/Wallpapers/unsplash-phIFdC6lA4E.jpg"
if [ ! -f "$WALLPAPER_FILE" ]; then
  echo "Downloading wallpaper..."
  mkdir -p ~/Pictures/Wallpapers && wget --content-disposition -P ~/Pictures/Wallpapers "https://unsplash.com/photos/phIFdC6lA4E/download?ixid=M3wxMjA3fDB8MXxhbGx8fHx8fHx8fHwxNzQzODUwMjgyfA&force=true"
else
  echo "Wallpaper already downloaded, skipping"
fi

# Arc HiDPI themes
if [ ! -d "$HOME/.themes/Arc-Dark" ]; then
  echo "Installing Arc HiDPI themes..."
  TMPDIR=$(mktemp -d) && wget -q -O - "https://master.dl.sourceforge.net/project/arc-xfwm4-hidpi/arc-theme-xfwm4-hidpi.tar.gz?viasf=1" | tar -xz -C "$TMPDIR" && mkdir -p ~/.themes && mv "$TMPDIR"/Arc* ~/.themes/ && rm -rf "$TMPDIR" && echo "Arc HiDPI themes installed into ~/.themes/"
else
  echo "Arc HiDPI themes already installed, skipping"
fi

# Brave browser
install_if_missing brave-browser "Brave browser" "curl -fsS https://dl.brave.com/install.sh | sh"

# フォント設定
sudo mkdir -p /usr/share/fonts

# Firgeフォント
if [ ! -f /usr/share/fonts/Firge35NerdConsole-Regular.ttf ]; then
    echo "Firgeフォントをインストールしています..."
    FIRGE_VERSION="0.2.0"
    wget -O /tmp/firge.zip "https://github.com/yuru7/Firge/releases/download/v${FIRGE_VERSION}/FirgeNerd_v${FIRGE_VERSION}.zip"
    mkdir -p /tmp/firge
    unzip -o /tmp/firge.zip -d /tmp/firge
    sudo cp /tmp/firge/FirgeNerd_v${FIRGE_VERSION}/*.ttf /usr/share/fonts/
    rm -rf /tmp/firge /tmp/firge.zip
    fc-cache -f -v
else
    echo "Firgeフォントはすでにインストールされています。スキップします。"
fi

# RobotoNotoSansJP
if [ ! -f /usr/share/fonts/Roboto-NotoSansJP-Regular.ttf ]; then
    echo "RobotoNotoSansJPフォントをインストールしています..."
    [ -d /tmp/robotonoto ] && rm -rf /tmp/robotonoto
    git clone --depth 1 https://github.com/reindex-ot/RobotoNotoSansJP.git /tmp/robotonoto
    sudo cp /tmp/robotonoto/*.ttf /usr/share/fonts/
    rm -rf /tmp/robotonoto
    fc-cache -f -v
else
    echo "RobotoNotoSansJPフォントはすでにインストールされています。スキップします。"
fi

# アプリケーションのインストール
install_if_missing starship starship "curl -sS https://starship.rs/install.sh | sh"
install_if_missing sheldon sheldon "curl --proto '=https' -fLsS https://rossmacarthur.github.io/install/crate.sh | bash -s -- --repo rossmacarthur/sheldon --to ~/.local/bin --force"

# Neovim
if ! command -v nvim &> /dev/null && [ ! -d "$HOME/.local/share/nvim-linux-x86_64" ]; then
    echo "Installing Neovim..."
    curl -LO https://github.com/neovim/neovim/releases/latest/download/nvim-linux-x86_64.tar.gz
    mkdir -p ~/.local/share
    tar -xzf nvim-linux-x86_64.tar.gz -C ~/.local/share/
    
    grep -q 'export PATH="$HOME/.local/share/nvim-linux-x86_64/bin:$PATH"' ~/.zshrc || 
      echo 'export PATH="$HOME/.local/share/nvim-linux-x86_64/bin:$PATH"' >> ~/.zshrc
    
    rm nvim-linux-x86_64.tar.gz
    echo "Neovim installed to ~/.local/share/, PATH added to ~/.zshrc."
else
    echo "Neovim already installed, skipping"
fi

# Slack
install_if_missing slack Slack "sudo snap refresh snapd || true && sudo snap install slack --classic"

# 1Password
install_if_missing 1password 1Password "wget -O /tmp/1password-latest.deb \"https://downloads.1password.com/linux/debian/amd64/stable/1password-latest.deb\" && sudo dpkg -i /tmp/1password-latest.deb && sudo apt-get install -f -y && rm /tmp/1password-latest.deb"

# wavemon
if ! command -v wavemon &> /dev/null; then
    echo "Installing wavemon (wireless monitoring tool)..."
    
    if sudo apt-get install -y wavemon; then
        sudo chmod u+s $(which wavemon)
        echo "wavemon installed successfully via apt with scanning privileges."
    else
        echo "apt installation failed, building wavemon from source..."
        sudo apt-get install -y pkg-config libncursesw6 libtinfo6 libncurses-dev libnl-cli-3-dev
        WAVEMON_TMP=$(mktemp -d)
        git clone --depth 1 https://github.com/uoaerg/wavemon.git "$WAVEMON_TMP"
        cd "$WAVEMON_TMP"
        ./configure && make && sudo make install-suid-root
        cd - > /dev/null
        rm -rf "$WAVEMON_TMP"
        echo "wavemon built and installed from source with scanning privileges."
    fi
elif [ -x "$(which wavemon)" ] && [ ! -u "$(which wavemon)" ]; then
    echo "Setting proper permissions for wavemon..."
    sudo chmod u+s $(which wavemon)
else
    echo "wavemon already installed with proper permissions, skipping"
fi