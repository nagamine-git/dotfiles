#!/usr/bin/env bash

# 未定義な変数があったら途中で終了する
set -u

# 今のディレクトリ
# dotfilesディレクトリに移動する
BASEDIR=$(dirname $0)
cd $BASEDIR

cp -f config.fish ~/.config/fish/config.fish
cp -f dot.init.vim ~/.config/nvim/init.vim
cp -f dot.tmux.conf ~/.tmux.conf
