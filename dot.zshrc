# パスの設定（oh-my-zshのインストール先を指定）
export ZSH="$HOME/.oh-my-zsh"

# テーマの設定（独自のプロンプトを使用するため、テーマは無効化）
ZSH_THEME=""

# プラグインの設定（必要なプラグインを指定）
plugins=(
    git
    zsh-autosuggestions
    zsh-syntax-highlighting
)

# oh-my-zshの読み込み
source $ZSH/oh-my-zsh.sh

# オプションの設定
setopt autocd              # ディレクトリ名を入力するだけで移動
setopt interactivecomments # 対話モードでのコメントを許可
setopt magicequalsubst     # ‘anything=expression’形式の引数でファイル名展開を有効にする
setopt nonomatch           # パターンに一致するものがない場合のエラーメッセージを非表示
setopt notify              # バックグラウンドジョブのステータスを即時に報告
setopt numericglobsort     # 数値的に意味がある場合、ファイル名を数値順にソート
setopt promptsubst         # プロンプトでのコマンド置換を有効にする

# WORDCHARSから'/'を削除
WORDCHARS=${WORDCHARS//\/}

# 行末記号を非表示にする
PROMPT_EOL_MARK=""

# 環境変数の設定
export LSCOLORS="ExGxFxdxCxDxDxhbHbHbHbHbHbHbHbHbH"
export LANG=ja_JP.UTF-8
export EDITOR=nvim

# キーバインドの設定
bindkey -e                                        # Emacsキーバインド
bindkey ' ' magic-space                           # スペースでヒストリー展開
bindkey '^U' backward-kill-line                   # Ctrl + U
bindkey '^[[3;5~' kill-word                       # Ctrl + Supr
bindkey '^[[3~' delete-char                       # Deleteキー
bindkey '^[[1;5C' forward-word                    # Ctrl + →
bindkey '^[[1;5D' backward-word                   # Ctrl + ←
bindkey '^[[5~' beginning-of-buffer-or-history    # Page Up
bindkey '^[[6~' end-of-buffer-or-history          # Page Down
bindkey '^[[H' beginning-of-line                  # Homeキー
bindkey '^[[F' end-of-line                        # Endキー
bindkey '^[[Z' undo                               # Shift + Tabで最後の操作を元に戻す

# 補完機能の有効化と設定
autoload -Uz compinit
compinit -d ~/.cache/zcompdump
zstyle ':completion:*:*:*:*:*' menu select
zstyle ':completion:*' auto-description 'specify: %d'
zstyle ':completion:*' completer _expand _complete
zstyle ':completion:*' format 'Completing %d'
zstyle ':completion:*' group-name ''
zstyle ':completion:*' list-colors ''
zstyle ':completion:*' list-prompt %SAt %p: Hit TAB for more, or the character to insert%s
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}'
zstyle ':completion:*' rehash true
zstyle ':completion:*' select-prompt %SScrolling active: current selection at %p%s
zstyle ':completion:*' use-compctl false
zstyle ':completion:*' verbose true
zstyle ':completion:*:kill:*' command 'ps -u $USER -o pid,%cpu,tty,cputime,cmd'

# ヒストリーの設定
HISTFILE=~/.zsh_history
HISTSIZE=1000
SAVEHIST=2000
setopt hist_expire_dups_first # ヒストリーファイルがHISTSIZEを超えた場合、重複を先に削除
setopt hist_ignore_dups       # 重複したコマンドを無視
setopt hist_ignore_space      # スペースで始まるコマンドを無視
setopt hist_verify            # ヒストリー展開後にコマンドを表示
setopt share_history          # ヒストリーデータを共有

# ヒストリーを完全に表示
alias history="history 0"

# エイリアスの設定
alias ls='eza'
alias ll='ls -l'
alias la='ls -A'
alias l='ls -CF'
alias vim='nvim'

# `time`コマンドのフォーマット設定
TIMEFMT=$'\nreal\t%E\nuser\t%U\nsys\t%S\ncpu\t%P'

# chroot環境の識別（プロンプトで使用）
if [ -z "${debian_chroot:-}" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
fi

# 仮想環境のプロンプト表示を無効化
VIRTUAL_ENV_DISABLE_PROMPT=1

# プロンプトのバリエーション設定
PROMPT_ALTERNATIVE=twoline
NEWLINE_BEFORE_PROMPT=yes

configure_prompt() {
    prompt_symbol=
    case "$PROMPT_ALTERNATIVE" in
        twoline)
            PROMPT=$'%F{%(#.blue.green)}┌──${debian_chroot:+($debian_chroot)─}${VIRTUAL_ENV:+($(basename $VIRTUAL_ENV))─}(%B%F{%(#.red.blue)}%n'$prompt_symbol$'%m%b%F{%(#.blue.green)})-[%B%F{reset}%(6~.%-1~/…/%4~.%5~)%b%F{%(#.blue.green)}]\n└─%B%(#.%F{red}#.%F{blue}$)%b%F{reset} '
            ;;
        oneline)
            PROMPT=$'${debian_chroot:+($debian_chroot)}${VIRTUAL_ENV:+($(basename $VIRTUAL_ENV))}%B%F{%(#.red.blue)}%n@%m%b%F{reset}:%B%F{%(#.blue.green)}%~%b%F{reset}%(#.#.$) '
            RPROMPT=
            ;;
        backtrack)
            PROMPT=$'${debian_chroot:+($debian_chroot)}${VIRTUAL_ENV:+($(basename $VIRTUAL_ENV))}%B%F{red}%n@%m%b%F{reset}:%B%F{blue}%~%b%F{reset}%(#.#.$) '
            RPROMPT=
            ;;
    esac
    unset prompt_symbol
}

configure_prompt

# シンタックスハイライトのスタイル設定
ZSH_HIGHLIGHT_HIGHLIGHTERS=(main brackets pattern)
ZSH_HIGHLIGHT_STYLES[default]=none
ZSH_HIGHLIGHT_STYLES[unknown-token]=underline
ZSH_HIGHLIGHT_STYLES[reserved-word]=fg=cyan,bold
# （以下、必要に応じてスタイル設定を追加してください）

# プロンプトの切り替え関数とキーバインド
toggle_oneline_prompt(){
    if [ "$PROMPT_ALTERNATIVE" = oneline ]; then
        PROMPT_ALTERNATIVE=twoline
    else
        PROMPT_ALTERNATIVE=oneline
    fi
    configure_prompt
    zle reset-prompt
}
zle -N toggle_oneline_prompt
bindkey ^P toggle_oneline_prompt

# ターミナルのタイトルを設定
case "$TERM" in
    xterm*|rxvt*|Eterm|aterm|kterm|gnome*|alacritty)
        TERM_TITLE=$'\e]0;${debian_chroot:+($debian_chroot)}${VIRTUAL_ENV:+($(basename $VIRTUAL_ENV))}%n@%m: %~\a'
        ;;
    *)
        ;;
esac

# プロンプト表示前の処理
precmd() {
    print -Pnr -- "$TERM_TITLE"

    if [ "$NEWLINE_BEFORE_PROMPT" = yes ]; then
        if [ -z "$_NEW_LINE_BEFORE_PROMPT" ]; then
            _NEW_LINE_BEFORE_PROMPT=1
        else
            print ""
        fi
    fi
}

# zsh-autosuggestionsのハイライトスタイル
ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=#999'

# command-not-foundの有効化
if [ -f /etc/zsh_command_not_found ]; then
    . /etc/zsh_command_not_found
fi

# fpathの設定
fpath+=${ZDOTDIR:-~}/.zsh_functions

# ASDFの設定
export ASDF_DIR="/opt/homebrew/Cellar/asdf/0.14.1/libexec"
source "/opt/homebrew/opt/asdf/libexec/asdf.sh"

# Rustのパス設定
[[ ! "$PATH" == *"/Users/nagamine/.asdf/installs/rust/1.72.0/bin"* ]] && export PATH="/Users/nagamine/.asdf/installs/rust/1.72.0/bin:$PATH"

# パスの追加
export PATH="$PATH:/Users/nagamine/.bin:$HOME/.gem/bin:/Users/nagamine/development/flutter/bin"
source /Users/nagamine/.config/broot/launcher/bash/br
eval "$(zoxide init zsh)"

# ghq/fzf/eza 組み合わせ
function ghq-fzf_change_directory() {
    # 選択したリポジトリへ移動 かつ
    # 右にリポジトリのディレクトリ詳細を表示
  local src=$(ghq list | fzf --preview "eza -l -g -a --icons $(ghq root)/{} | tail -n+4 | awk '{print \$6\"/\"\$8\" \"\$9 \" \" \$10}'")
  if [ -n "$src" ]; then
    BUFFER="cd $(ghq root)/$src"
    zle accept-line
  fi
  zle -R -c
}

zle -N ghq-fzf_change_directory
bindkey '^f' ghq-fzf_change_directory

# Zsh History Substring Search
source $(brew --prefix)/share/zsh-history-substring-search/zsh-history-substring-search.zsh
autoload -U history-substring-search
bindkey "${terminfo[kcuu1]}" history-substring-search-up
bindkey "${terminfo[kcud1]}" history-substring-search-down

# .envファイルの読み込み
if [ -f ~/.env ]; then
    set -a
    source ~/.env
    set +a
fi

