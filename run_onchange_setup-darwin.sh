#!/bin/bash

set -eu # エラー時や未定義変数使用時にスクリプトを終了させる

SOURCE_DIR="$HOME/.local/share/chezmoi"
BREW_PACKAGE_LIST_FILE="$SOURCE_DIR/private_dot_config/chezmoi/brew-packages.txt"

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

# Homebrewのインストールチェック
if ! command -v brew &> /dev/null; then
  echo "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)"
else
  echo "Homebrew already installed, skipping"
fi

# brew-packages.txtの存在確認
if [ ! -f "$BREW_PACKAGE_LIST_FILE" ]; then
  echo "brew-packages.txt not found at $BREW_PACKAGE_LIST_FILE"
  echo "Please create the file or run 'chezmoi init' again."
  exit 1
fi

# Homebrewの更新
echo "Updating Homebrew..."
brew update

# Homebrewパッケージのインストール
if [ -f "$BREW_PACKAGE_LIST_FILE" ]; then
  echo "Installing packages from $BREW_PACKAGE_LIST_FILE..."
  
  while read -r package; do
    [[ "$package" =~ ^#.*$ || -z "$package" ]] && continue
    
    if ! brew list "$package" &> /dev/null; then
      echo "Installing $package..."
      brew install "$package"
    else
      echo "Package $package already installed, skipping"
    fi
  done < <(grep -v '^#' "$BREW_PACKAGE_LIST_FILE" | grep -v '^\s*$')
else
  echo "Warning: brew-packages.txt not found at $BREW_PACKAGE_LIST_FILE"
fi

# クリーンアップ
echo "brew package installation process finished."
echo "Running brew cleanup..."
brew cleanup

# ロケールの設定
if ! locale -a | grep -q 'ja_JP.utf8' && ! locale -a | grep -q 'ja_JP.UTF-8'; then
  echo "Japanese locale may need to be enabled in System Settings > Language & Region"
fi

# zshの確認
if [[ "$SHELL" != *"zsh" ]]; then
  echo "Setting shell to zsh..."
  chsh -s /bin/zsh
else
  echo "Shell already set to zsh, skipping"
fi

# GitHub CLI認証
gh auth status || gh auth login

# Node.js (mise経由)
if command -v mise &> /dev/null; then
  echo "Installing Node.js via mise..."
  mise install node@lts
fi

# Pythonのセットアップ (mise経由)
if command -v mise &> /dev/null; then
  echo "Installing Python via mise..."
  mise install python@latest
fi

# フォント設定
FONT_DIR="$HOME/Library/Fonts"
mkdir -p "$FONT_DIR"

# Firgeフォント
if ! find "$FONT_DIR" -name "*Firge*Nerd*.ttf" | grep -q .; then
  echo "Firgeフォントをインストールしています..."
  
  # GitHub APIを使用して最新バージョンを取得
  LATEST_RELEASE_INFO=$(curl -s https://api.github.com/repos/yuru7/Firge/releases/latest)
  FIRGE_VERSION=$(echo $LATEST_RELEASE_INFO | grep -o '"tag_name": "[^"]*' | cut -d'"' -f4 | sed 's/^v//')
  
  if [ -z "$FIRGE_VERSION" ]; then
    FIRGE_VERSION="0.3.0"
    echo "最新バージョンの取得に失敗しました。バージョン ${FIRGE_VERSION} を使用します。"
  else
    echo "最新バージョン ${FIRGE_VERSION} を使用します。"
  fi
  
  wget -O /tmp/firge.zip "https://github.com/yuru7/Firge/releases/download/v${FIRGE_VERSION}/FirgeNerd_v${FIRGE_VERSION}.zip"
  mkdir -p /tmp/firge
  unzip -o /tmp/firge.zip -d /tmp/firge
  cp /tmp/firge/FirgeNerd_v${FIRGE_VERSION}/*.ttf "$FONT_DIR/"
  rm -rf /tmp/firge /tmp/firge.zip
else
  echo "Firgeフォントはすでにインストールされています。"
fi

# プラグインマネージャー関連
# sheldon
install_if_missing sheldon sheldon "cargo install sheldon --locked"

# starship
install_if_missing starship starship "curl -sS https://starship.rs/install.sh | sh"

echo "Mac setup completed!"

# window manager
# echo "$(whoami) ALL=(root) NOPASSWD: $(which yabai) --load-sa" \
#   | sudo tee /etc/sudoers.d/yabai
# yabai --start-service
# skhd --start-service