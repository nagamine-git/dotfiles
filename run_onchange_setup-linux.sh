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
# Install packages only if they're not already installed
while read -r package; do
  # Skip comments and empty lines
  [[ "$package" =~ ^#.*$ || -z "$package" ]] && continue
  
  if ! dpkg -l | grep -q "^ii  $package "; then
    sudo apt install -y "$package"
    echo "Installed $package"
  else
    echo "Package $package already installed, skipping"
  fi
done < <(grep -v '^#' "$PACKAGE_LIST_FILE" | grep -v '^\s*$')

echo "apt package installation process finished."

# 必要であれば、古いパッケージの削除なども追加できる
echo "Running apt autoremove..."
sudo apt autoremove -y
echo "Running apt clean..."
sudo apt clean
sudo snap install snapd

# Create symbolic links for Snap applications in Xfce menu
echo "Setting up Snap applications in Xfce menu..."
if [ ! -d "/var/lib/snapd/desktop/applications" ]; then
    echo "Snap applications directory not found, skipping menu setup"
else
    # Remove any existing broken links first
    sudo find /usr/share/applications -xtype l -delete
    # Create symbolic links for all Snap desktop entries
    sudo ln -sf /var/lib/snapd/desktop/applications/*.desktop /usr/share/applications/
    echo "Snap applications added to Xfce menu"
fi

# zsh 
if [ "$SHELL" != "/bin/zsh" ]; then
  echo "Changing shell to zsh..."
  chsh -s /bin/zsh
else
  echo "Shell already set to zsh, skipping"
fi

# mise
if ! command -v mise &> /dev/null; then
  echo "Installing mise..."
  curl https://mise.run | sh
  
  echo "Running mise i..."
else
  echo "mise already installed, skipping"
fi
mise i

# GitHub CLI (gh)のインストール
if ! command -v gh &> /dev/null; then
    echo "Installing GitHub CLI (gh)..."
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
    sudo apt update
    sudo apt install gh -y
else
    echo "GitHub CLI (gh) already installed, skipping"
fi

# gh auth login
if ! gh auth status; then
  gh auth login
fi

# cargo(using mise)
cargo install sheldon

# ghqのインストール
if ! command -v ghq &> /dev/null; then
    echo "Installing ghq..."
    go install github.com/x-motemen/ghq@latest
else
    echo "ghq already installed, skipping"
fi

# gh-q拡張機能のインストール
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
if ! command -v brave-browser &> /dev/null; then
  echo "Installing Brave browser..."
  curl -fsS https://dl.brave.com/install.sh | sh
else
  echo "Brave browser already installed, skipping"
fi

# フォント設定
sudo mkdir -p /usr/share/fonts

# Firgeフォントのインストール
if [ ! -f /usr/share/fonts/Firge35NerdConsole-Regular.ttf ]; then
    echo "Firgeフォントをインストールしています..."

    # Firge35Nerd Consoleをダウンロード
    FIRGE_VERSION="0.2.0"
    FIRGE_URL="https://github.com/yuru7/Firge/releases/download/v${FIRGE_VERSION}/FirgeNerd_v${FIRGE_VERSION}.zip"
    wget -O /tmp/firge.zip "$FIRGE_URL"

    # 解凍して配置
    mkdir -p /tmp/firge
    unzip -o /tmp/firge.zip -d /tmp/firge
    sudo cp /tmp/firge/FirgeNerd_v${FIRGE_VERSION}/*.ttf /usr/share/fonts/

    # 片付け
    rm -rf /tmp/firge /tmp/firge.zip
    
    # フォントキャッシュの更新
    fc-cache -f -v
else
    echo "Firgeフォントはすでにインストールされています。スキップします。"
fi

# RobotoNotoSansJPフォントのインストール
if [ ! -f /usr/share/fonts/Roboto-NotoSansJP-Regular.ttf ]; then
    echo "RobotoNotoSansJPフォントをインストールしています..."

    # 既存のディレクトリがあれば削除
    if [ -d /tmp/robotonoto ]; then
        rm -rf /tmp/robotonoto
    fi

    # リポジトリをクローンして必要なファイルをコピー
    git clone --depth 1 https://github.com/reindex-ot/RobotoNotoSansJP.git /tmp/robotonoto
    sudo cp /tmp/robotonoto/*.ttf /usr/share/fonts/

    # 片付け
    rm -rf /tmp/robotonoto
    
    # フォントキャッシュの更新
    fc-cache -f -v
else
    echo "RobotoNotoSansJPフォントはすでにインストールされています。スキップします。"
fi

# starship
if ! command -v starship &> /dev/null; then
    echo "Installing starship..."
    curl -sS https://starship.rs/install.sh | sh
else
    echo "starship already installed, skipping"
fi

# sheldon
if ! command -v sheldon &> /dev/null; then
    echo "Installing sheldon..."
    curl --proto '=https' -fLsS https://rossmacarthur.github.io/install/crate.sh \
        | bash -s -- --repo rossmacarthur/sheldon --to ~/.local/bin --force
else
    echo "sheldon already installed, skipping"
fi

# Neovim
if ! command -v nvim &> /dev/null && [ ! -d "$HOME/.local/share/nvim-linux-x86_64" ]; then
    echo "Installing Neovim..."
    curl -LO https://github.com/neovim/neovim/releases/latest/download/nvim-linux-x86_64.tar.gz
    mkdir -p ~/.local/share
    tar -xzf nvim-linux-x86_64.tar.gz -C ~/.local/share/
    
    # Check if PATH export already exists in .zshrc
    if ! grep -q 'export PATH="$HOME/.local/share/nvim-linux-x86_64/bin:$PATH"' ~/.zshrc; then
        echo 'export PATH="$HOME/.local/share/nvim-linux-x86_64/bin:$PATH"' >> ~/.zshrc
    fi
    
    rm nvim-linux-x86_64.tar.gz
    echo "Neovim installed to ~/.local/share/, PATH added to ~/.zshrc. Run 'source ~/.zshrc' or open a new Zsh terminal to use the 'nvim' command."
else
    echo "Neovim already installed, skipping"
fi

# Install Slack
if ! command -v slack &> /dev/null; then
    echo "Installing Slack..."
    
    # Make sure snapd is up to date
    echo "Refreshing snapd..."
    sudo snap refresh snapd || true    
    sudo snap install slack --classic
else
    echo "Slack already installed, skipping"
fi

if ! command -v 1password &> /dev/null; then
    echo "Installing 1Password..."
    wget -O /tmp/1password-latest.deb "https://downloads.1password.com/linux/debian/amd64/stable/1password-latest.deb"
    sudo dpkg -i /tmp/1password-latest.deb
    sudo apt-get install -f -y # Install dependencies if needed
    rm /tmp/1password-latest.deb
    echo "1Password installed successfully."
else
    echo "1Password already installed, skipping"
fi

# Install wavemon with elevated privileges
if ! command -v wavemon &> /dev/null; then
    echo "Installing wavemon (wireless monitoring tool)..."
    
    # Try installing via apt first
    if sudo apt-get install -y wavemon; then
        # Make it suid-root for scanning permissions
        sudo chmod u+s $(which wavemon)
        echo "wavemon installed successfully via apt with scanning privileges."
    else
        echo "apt installation failed, building wavemon from source..."
        
        # Install dependencies
        sudo apt-get install -y pkg-config libncursesw6 libtinfo6 libncurses-dev libnl-cli-3-dev
        
        # Create temp directory and clone repo
        WAVEMON_TMP=$(mktemp -d)
        git clone --depth 1 https://github.com/uoaerg/wavemon.git "$WAVEMON_TMP"
        
        # Build and install with suid privileges
        cd "$WAVEMON_TMP"
        ./configure && make
        sudo make install-suid-root
        
        # Clean up
        cd - > /dev/null
        rm -rf "$WAVEMON_TMP"
        echo "wavemon built and installed from source with scanning privileges."
    fi
else
    # If already installed, make sure it has proper privileges
    if [ -x "$(which wavemon)" ] && [ ! -u "$(which wavemon)" ]; then
        echo "Setting proper permissions for wavemon..."
        sudo chmod u+s $(which wavemon)
    else
        echo "wavemon already installed with proper permissions, skipping"
    fi
fi