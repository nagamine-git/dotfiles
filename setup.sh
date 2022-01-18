#!/usr/bin/env bash

# 未定義な変数があったら途中で終了する
set -u

# dotfilesディレクトリに移動する
BASEDIR=$(pwd)
cd $BASEDIR

ln -snfv $BASEDIR/config.fish ${HOME}/.config/fish/config.fish
ln -snfv $BASEDIR/init.vim ${HOME}/.config/nvim/init.vim
ln -snfv $BASEDIR/dot.tmux.conf ${HOME}/.tmux.conf
ln -snfv $BASEDIR/dot.tmuxline.conf ${HOME}/.tmuxline.conf

