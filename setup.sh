#!/usr/bin/env bash

# 未定義な変数があったら途中で終了する
set -u

# 今のディレクトリ
# dotfilesディレクトリに移動する
BASEDIR=$(dirname $0)
cd $BASEDIR

ln -sf config.fish ~/.config/fish/config.fish
ln -sf dot.init.vim ~/.config/nvim/init.vim
ln -sf dot.tmux.conf ~/.tmux.conf
