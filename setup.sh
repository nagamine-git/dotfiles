#!/usr/bin/env bash

# 未定義な変数があったら途中で終了する
set -u

# dotfilesディレクトリに移動する
BASEDIR=$(pwd)
cd $BASEDIR

ln -snfv $BASEDIR/config ${HOME}/.config
ln -snfv $BASEDIR/dot.tmux.conf ${HOME}/.tmux.conf
ln -snfv $BASEDIR/dot.tmuxline.conf ${HOME}/.tmuxline.conf
ln -snfv $BASEDIR/dot.gitconfig ${HOME}/.gitconfig

