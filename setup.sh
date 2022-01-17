#!/bin/bash

# 連想配列の宣言
declare -A FILES;
# ファイル名:パス名
FILES=(
  ["dot.init.vim"]="$HOME/.config/nvim/init.vim"
  ["dot.tmux.conf"]="$HOME/.tmux.conf"
  ["config.fish"]="$HOME/.config/fish/config.fish"
)
# 連想配列のループ
for FILE in ${!FILES[@]};
do
    echo ${FILES[$FILE]}
    ln -nfsv ./$FILE ${FILES[$FILE]}
done
exit 0
