#!/bin/bash
# Install Tmux Plugin Manager (TPM)
set -eu

TPM_DIR="$HOME/.tmux/plugins/tpm"

if [ ! -d "$TPM_DIR/.git" ]; then
  # .git の有無で判定 (clone 中断による不完全ディレクトリを検出して再取得)
  rm -rf "$TPM_DIR"
  echo "Installing TPM..."
  git clone https://github.com/tmux-plugins/tpm "$TPM_DIR"
else
  echo "TPM already installed, skipping"
fi
