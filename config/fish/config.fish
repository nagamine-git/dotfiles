# set ls colors
export LSCOLORS=gxfxcxdxbxegedabagacad

# set Language
set -x LANG ja_JP.UTF-8

# Aliases
# [ ls]
alias ls='ls -F --color=auto'
#[ vim ]
alias v='nvim'
#[ vim ]
alias vi='nvim'
#[ nvim ]
alias vim='nvim'
#[ yarn ]
alias y='yarn'
#[ system ]
alias ds='sudo pmset -a disablesleep 1 && echo "スリープは無効になってます"'
alias as='sudo pmset -a disablesleep 0 && echo "通常の状態です"'
#[docker]
alias d docker
alias dc docker-compose
alias dce='docker-compose exec'
#[ ghq ]
alias gg='cd (ghq root)/(ghq list | peco)'
alias ggh='hub browse (ghq list | peco | cut -d "/" -f 2,3)'
alias ggt='cd (ghq root)/(ghq list | peco) && tmux'
#[ git ]
alias g='git'
#compdef g=git
alias gst='git status'
#compdef _git gst=git-status
alias gf='git fetch'
#compdef _git gf=git-fetch
alias gd='git diff'
#compdef _git gd=git-diff
alias gdc='git diff --cached'
#compdef _git gdc=git-diff
alias gl='git pull'
#compdef _git gl=git-pull
alias glo='git pull origin'
#compdef _git glo=git-pull-origin
alias gup='git pull --rebase'
#compdef _git gup=git-fetch
alias gp='git push'
#compdef _git gp=git-push
alias gpo='git push origin'
#compdef _git gpo=git-push-origin
alias gd='git diff'
function gdv
  git diff -w $argv | view -
end
#compdef _git gdv=git-diff
alias gc='git commit -v'
#compdef _git gc=git-commit
alias gc!='git commit -v --amend'
#compdef _git gc!=git-commit
alias gca='git commit -v -a'
#compdef _git gc=git-commit
alias gca!='git commit -v -a --amend'
#compdef _git gca!=git-commit
alias gce='git commit --allow-empty -m "empty commit"'
alias gcmsg='git commit -m'
#compdef _git gcmsg=git-commit
alias gco='git checkout'
#compdef _git gco=git-checkout
alias gcm='git checkout master'
alias gr='git remote'
#compdef _git gr=git-remote
alias grv='git remote -v'
#compdef _git grv=git-remote
alias grmv='git remote rename'
#compdef _git grmv=git-remote
alias grrm='git remote remove'
#compdef _git grrm=git-remote
alias grset='git remote set-url'
#compdef _git grset=git-remote
alias grup='git remote update'
#compdef _git grset=git-remote
alias grbi='git rebase -i'
#compdef _git grbi=git-rebase
alias grbc='git rebase --continue'
#compdef _git grbc=git-rebase
alias grba='git rebase --abort'
#compdef _git grba=git-rebase
alias gb='git branch'
#compdef _git gb=git-branch
alias gba='git branch -a'
#compdef _git gba=git-branch
alias gcount='git shortlog -sn'
#compdef gcount=git
alias gcl='git config --list'
alias gcp='git cherry-pick'
#compdef _git gcp=git-cherry-pick
alias glo='git log --oneline'
# compdef _git glog=git-log
alias glod="git log --no-merges --oneline --reverse"
# compdef _git glod=git-log
alias glg='git log --graph --pretty=format:"%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset"'
#compdef _git glo=git-log
alias glga='git log --graph --all --pretty=format:"%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset"'
# compdef _git glo=git-log
alias gss='git status -s'
#compdef _git gss=git-status
alias ga='git add'
#compdef _git gaa=git-add-all
alias gaa='git add -A'
#compdef _git ga=git-add
alias gm='git merge'
#compdef _git gm=git-merge
alias gmt='git mergetool -t vimdiff'
#compdef _git gmt=git-mergetool
alias grh='git reset HEAD'
alias grhh='git reset HEAD --hard'
alias grsh='git reset HEAD^ --soft'
alias gclean='git reset --hard; and git clean -df'
alias gwc='git whatchanged -p --abbrev-commit --pretty=medium'
alias gsts='git stash show --text'
alias gsta='git stash'
alias gstp='git stash pop'
alias gstd='git stash drop'

function current_branch
  set ref (git symbolic-ref HEAD 2> /dev/null); or \
  set ref (git rev-parse --short HEAD 2> /dev/null); or return
  echo ref | sed s-refs/heads--
end
function current_repository
  set ref (git symbolic-ref HEAD 2> /dev/null); or \
  set ref (git rev-parse --short HEAD 2> /dev/null); or return
  echo (git remote -v | cut -d':' -f 2)
end
# these aliases take advantage of the previous function
alias ggpull='git pull origin $current_branch'
#compdef ggpull=git
alias ggpur='git pull --rebase origin $current_branch'
#compdef ggpur=git
alias ggpush='git push origin $current_branch'
#compdef ggpush=git
alias ggpnp='git pull origin $current_branch; and git push origin $current_branch'
#compdef ggpnp=git
# Pretty log messages
function _git_log_prettily
  if ! [ -z $1 ]; then
    git log --pretty=$1
  end
end
alias glp="_git_log_prettily"
#compdef _git glp=git-log
# Work In Progress (wip)
# These features allow to pause a branch development and switch to another one (wip)
# When you want to go back to work, just unwip it
#
# This function return a warning if the current branch is a wip
function work_in_progress
  if git log -n 1 | grep -q -c wip; then
    echo "WIP!!"
  end
end
# these alias commit and uncomit wip branches
alias gwip='git add -A; git ls-files --deleted -z | xargs -0 git rm; git commit -m "wip"'
alias gunwip='git log -n 1 | grep -q -c wip; and git reset HEAD~1'

source /usr/local/opt/asdf/asdf.fish

# terminal-notifier
alias notification-banner-clear='terminal-notifier -remove ALL'

function notify
  notification-banner-clear > /dev/null
  terminal-notifier -title "☑️ Process has ended!" -message "Please check the output" -sound Glass
end
