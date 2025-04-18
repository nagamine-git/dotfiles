#!/bin/bash

set -eu # エラー時や未定義変数使用時にスクリプトを終了させる

SOURCE_DIR='/home/tsuyoshi/.local/share/chezmoi'
PACKAGE_LIST_FILE="$SOURCE_DIR/private_dot_config/chezmoi/apt-packages.txt"

# 汎用インストール関数
install_if_missing() {
  local cmd=$1
  local name=${2:-$1}
  local install_cmd=$3

  echo "=== Debug: install_if_missing check ==="
  echo "Checking command: $cmd"
  echo "Package name: $name"
  echo "Install command: $install_cmd"
  
  if ! command -v "$cmd" &> /dev/null; then
    echo "Command '$cmd' not found in PATH"
    echo "Current PATH: $PATH"
    echo "Installing $name..."
    eval "$install_cmd"
  else
    echo "Command '$cmd' found at: $(which "$cmd")"
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
echo "=== Debug: Installing packages from $PACKAGE_LIST_FILE ==="
echo "File contents:"
cat "$PACKAGE_LIST_FILE"
echo "---"

while read -r package; do
  [[ "$package" =~ ^#.*$ || -z "$package" ]] && continue
  
  echo "=== Debug: Processing package: $package ==="
  echo "Running: dpkg -l | grep \"^ii  $package \""
  dpkg -l | grep "^ii  $package " || echo "Package not found in dpkg -l"
  
  if ! dpkg -l | grep -q "^ii  $package "; then
    echo "Installing $package..."
    sudo apt install -y "$package"
    echo "Installation completed with status: $?"
  else
    echo "Package $package already installed, skipping"
  fi
done < <(grep -v '^#' "$PACKAGE_LIST_FILE" | grep -v '^\s*$')

# クリーンアップ
echo "apt package installation process finished."
echo "Running apt autoremove & clean..."
sudo apt autoremove -y && sudo apt clean

# im-configでfcitx5を設定
if [ -x "$(command -v fcitx5)" ]; then
  im-config -n fcitx5
fi

# fcitx5-hazkeyの確認とインストール
if dpkg -s fcitx5-hazkey >/dev/null 2>&1; then
  HAZKEY_VERSION=$(dpkg-query -W -f='${Version}' fcitx5-hazkey)
  echo "fcitx5-hazkey is already installed (version: $HAZKEY_VERSION)"
else
  echo "Installing fcitx5-hazkey..."
  ARCH=$(dpkg --print-architecture)
  
  LATEST_RELEASE_INFO=$(curl -s https://api.github.com/repos/7ka-Hiira/fcitx5-hazkey/releases/latest)
  VERSION=$(echo $LATEST_RELEASE_INFO | grep -o '"tag_name": "[^"]*' | cut -d'"' -f4)
  DEB_URL=$(echo $LATEST_RELEASE_INFO | grep -o '"browser_download_url": "[^"]*\.deb"' | grep "$ARCH" | cut -d'"' -f4)
  
  if [ -n "$DEB_URL" ]; then
    echo "Downloading fcitx5-hazkey from $DEB_URL..."
    wget -O /tmp/fcitx5-hazkey.deb "$DEB_URL"
    sudo apt install -y /tmp/fcitx5-hazkey.deb
    rm /tmp/fcitx5-hazkey.deb
    echo "fcitx5-hazkey installed successfully"
  else
    echo "Error: Could not find fcitx5-hazkey package for $ARCH architecture"
  fi
fi

# Zenzaiに必要なVulkanドライバのインストール
echo "Installing Vulkan drivers for Zenzai..."
if ! dpkg -l | grep -q "^ii  vulkan-tools " || ! dpkg -l | grep -q "^ii  libvulkan1 " || ! dpkg -l | grep -q "^ii  mesa-vulkan-drivers "; then
  # apt-packages.txtに記載されているので、ここでのインストールは不要
  echo "Vulkan drivers installed successfully"
else
  echo "Vulkan drivers already installed, skipping"
fi

# snapdのセットアップ
if ! command -v snap &> /dev/null; then
    sudo apt install -y snapd
    sudo systemctl enable --now snapd.socket
fi

# ロケールの設定
if ! locale -a | grep -q 'ja_JP.utf8'; then
    echo "Generating Japanese locale..."
    sudo apt install -y language-pack-ja
    sudo locale-gen ja_JP.UTF-8
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

# gem
sudo gem install fusuma fusuma-plugin-remap fusuma-plugin-thumbsense fusuma-plugin-wmctrl fusuma-plugin-keypress fusuma-plugin-sendkey          sp

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
WALLPAPER_FILE="$HOME/Pictures/Wallpapers/benjamin-voros-phIFdC6lA4E-unsplash.jpg"
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

# fusumaのセットアップ
if command -v fusuma &> /dev/null; then
    echo "Configuring fusuma..."
    # ユーザーをinputグループに追加
    sudo usermod -a -G input $USER

    echo 'KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/60-udev-fusuma-remap.rules
    sudo udevadm control --reload-rules && sudo udevadm trigger
    
    # systemdサービスのセットアップ
    mkdir -p ~/.config/systemd/user/
    cp "$SOURCE_DIR/private_dot_config/systemd/user/fusuma.service" ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now fusuma.service
    echo "Fusuma configured and service enabled"
else
    echo "Fusuma not installed, skipping configuration"
fi

# XKBカスタム設定のセットアップ
echo "Setting up custom XKB layout..."
chmod +x ~/.local/bin/apply-custom-xkb.sh
mkdir -p ~/.config/autostart
~/.local/bin/apply-custom-xkb.sh
echo "Custom XKB layout setup complete"

# Dockerのインストール
echo "Installing Docker..."
if ! command -v docker &> /dev/null; then
    echo "Setting up Docker's apt repository..."
    # Docker公式GPGキーを追加
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    # リポジトリをAptソースに追加
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update

    # Dockerパッケージのインストール
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # ユーザーをdockerグループに追加（sudoなしでDockerを使用可能に）
    sudo groupadd -f docker
    sudo usermod -aG docker $USER

    # Docker自動起動を無効化
    sudo systemctl disable docker.service
    sudo systemctl enable docker.socket
    
    echo "Docker installation complete. You may need to log out and log back in to use Docker without sudo."
    echo "To verify Docker installation, run: docker run hello-world"
else
    echo "Docker is already installed, skipping"
fi