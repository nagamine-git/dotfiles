# Interactive shell check
[[ $- == *i* ]] && eval "$(/opt/homebrew/bin/brew shellenv)"

# Set ls colors
export LSCOLORS=gxfxcxdxbxegedabagacad
export LANG=ja_JP.UTF-8
export EDITOR=nvim

# Aliases
alias zping='while ! ping -c 3 google.com; do sleep 1; done; echo "Network is up!"'
alias zmtr='while ! sudo mtr -c 10 google.com; do sleep 1; done; echo "Network is up!"'
alias ls='ls -F --color=auto'
alias v='nvim'
alias vi='nvim'
alias vim='nvim'
alias vimdiff='nvim -d'
alias memo='nvim ~/memo.md'
alias y='yarn'
alias d='docker'
alias dc='docker compose'
alias dce='docker compose exec'

# [ ghq ]
alias gg='cd $(ghq root)/$(ghq list | peco)'
alias ggc='code . $(cd $(ghq root)/$(ghq list | peco))'
alias ggh='hub browse $(ghq list | peco | cut -d "/" -f 2,3)'

# [ git ]
alias g='git'
alias gst='git status'
alias gf='git fetch'
alias gd='git diff'
alias gdc='git diff --cached'
alias gl='git pull'
alias glo='git pull origin'
alias gup='git pull --rebase'
alias gp='git push'
alias gpo='git push origin'
alias gc='git commit -v'
alias gc!='git commit -v --amend'
alias gca='git commit -v -a'
alias gca!='git commit -v -a --amend'
alias gce='git commit --allow-empty -m "empty commit"'
alias gcmsg='git commit -m'
alias gco='git checkout'
alias gcm='git checkout master'
alias gr='git remote'
alias grv='git remote -v'
alias grmv='git remote rename'
alias grrm='git remote remove'
alias grset='git remote set-url'
alias grup='git remote update'
alias grbi='git rebase -i'
alias grbc='git rebase --continue'
alias grba='git rebase --abort'
alias gb='git branch'
alias gba='git branch -a'
alias gcount='git shortlog -sn'
alias gcl='git config --list'
alias gcp='git cherry-pick'
alias glo='git log --oneline'
alias glod='git log --no-merges --oneline --reverse'
alias glg='git log --graph --pretty=format:"%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset"'
alias glga='git log --graph --all --pretty=format:"%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset"'
alias gss='git status -s'
alias ga='git add'
alias gaa='git add -A'
alias gm='git merge'
alias gmt='git mergetool'
alias gdt='git difftool'
alias grh='git reset HEAD'
alias grhh='git reset HEAD --hard'
alias grsh='git reset HEAD^ --soft'
alias gclean='git reset --hard && git clean -df'
alias gwc='git whatchanged -p --abbrev-commit --pretty=medium'
alias gsts='git stash show --text'
alias gsta='git stash'
alias gstp='git stash pop'
alias gstd='git stash drop'

current_branch() {
  git symbolic-ref HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null
}

alias ggpull='git pull origin $(current_branch)'
alias ggpur='git pull --rebase origin $(current_branch)'
alias ggpush='git push origin $(current_branch)'
alias ggpnp='git pull origin $(current_branch) && git push origin $(current_branch)'

# Work In Progress (wip) functions
work_in_progress() {
  git log -n 1 | grep -q -c wip && echo "WIP!!"
}

alias gwip='git add -A && git ls-files --deleted -z | xargs -0 git rm && git commit -m "wip"'
alias gunwip='git log -n 1 | grep -q -c wip && git reset HEAD~1'

# Set ASDF_DIR and source asdf
export ASDF_DIR="/opt/homebrew/Cellar/asdf/0.12.0/libexec"
source "/opt/homebrew/opt/asdf/libexec/asdf.sh"

# terminal-notifier
alias notification-banner-clear='terminal-notifier -remove ALL'

notify() {
  notification-banner-clear > /dev/null
  terminal-notifier -title "☑️ Process has ended!" -message "Please check the output" -sound Glass
}

ggt() {
  prjflag=""
  [[ $# -gt 0 ]] && prjflag="--query \"$*\""
  PRJ_PATH="$(ghq root)/$(ghq list | peco $prjflag)"
  [[ -z "$PRJ_PATH" ]] && return
  PRJ_NAME=$(basename "$(dirname "$PRJ_PATH")")/$(basename "$PRJ_PATH" | sed -e 's/\./_/g')
  if ! tmux has-session -t "$PRJ_NAME"; then
    tmux new-session -c "$PRJ_PATH" -s "$PRJ_NAME" -d
    tmux setenv -t "$PRJ_NAME" TMUX_SESSION_PATH "$PRJ_PATH"
  fi
  [[ -z "$TMUX" ]] && tmux attach -t "$PRJ_NAME" || tmux switch-client -t "$PRJ_NAME"
}

# Rust setup for Zsh
[[ ! "$PATH" == *"/Users/nagamine/.asdf/installs/rust/1.72.0/bin"* ]] && export PATH="/Users/nagamine/.asdf/installs/rust/1.72.0/bin:$PATH"

export PATH="$PATH:/Users/nagamine/.bin:$HOME/.gem/bin:/Users/nagamine/development/flutter/bin"