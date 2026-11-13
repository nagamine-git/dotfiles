#!/usr/bin/env bash
# ~/AGENTS.md を ~/.config/agents/home-AGENTS.md へのシンボリックリンクにする。
# ソース直下の AGENTS.md はこのリポジトリ用なので、ホーム用の本文は別パスに置いている。
# リンク済みなら no-op。通常ファイルなら .bak.<日時> に退避してからリンクする。
set -eu

src="$HOME/.config/agents/home-AGENTS.md"
dst="$HOME/AGENTS.md"

link_home_agents() {
  if [ ! -f "$src" ]; then
    echo "WARN: $src がないためリンクをスキップ" >&2
    return 0
  fi
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    return 0
  fi
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then
    bak="$dst.bak.$(date +%Y%m%d%H%M%S)"
    mv "$dst" "$bak"
    echo "backup: $bak"
  fi
  ln -sfn "$src" "$dst"
  echo "linked: $dst -> $src"
}

link_home_agents
