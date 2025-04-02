# エミュレーションモードをチェックし、必要に応じて修正
if [[ "$(emulate)" != "zsh" ]]; then
  exec zsh
fi

# パスの設定（oh-my-zshのインストール先を指定）
export ZSH="$HOME/.oh-my-zsh"
export LANG=ja_JP.UTF-8
export LC_ALL=ja_JP.UTF-8

# ASDFの設定
export ASDF_DIR="$HOME/.asdf"
export ASDF_DATA_DIR="$HOME/.asdf"
export ASDF_CONFIG_FILE="$HOME/.asdfrc"
export ASDF_DEFAULT_TOOL_VERSIONS_FILENAME=".tool-versions"

# テーマの設定（独自のプロンプトを使用するため、テーマは無効化）
ZSH_THEME=""

# プラグインの設定（必要なプラグインを指定）
plugins=(
    git
    zsh-autosuggestions
    zsh-syntax-highlighting
    zsh-history-substring-search
)

# oh-my-zshの読み込み
source $ZSH/oh-my-zsh.sh

# オプションの設定
setopt autocd              # ディレクトリ名を入力するだけで移動
setopt interactivecomments # 対話モードでのコメントを許可
setopt magicequalsubst     # 'anything=expression'形式の引数でファイル名展開を有効にする
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

# 部分一致の履歴検索の設定
# プラグインの読み込み順序を確認
if [ -f ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-history-substring-search/zsh-history-substring-search.zsh ]; then
  source ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-history-substring-search/zsh-history-substring-search.zsh
fi

# 前方一致モードをオフにする
HISTORY_SUBSTRING_SEARCH_PREFIXED=""

# キーバインドの再設定
bindkey '^[[A' history-substring-search-up
bindkey '^[[B' history-substring-search-down
# 代替キーバインド（端末によって異なる場合）
bindkey "$terminfo[kcuu1]" history-substring-search-up
bindkey "$terminfo[kcud1]" history-substring-search-down

# ヒストリーの設定
HISTFILE=~/.zsh_history
HISTSIZE=1000
SAVEHIST=2000
setopt hist_expire_dups_first # ヒストリーファイルがHISTSIZEを超えた場合、重複を先に削除
setopt hist_ignore_dups       # 重複したコマンドを無視
setopt hist_ignore_space      # スペースで始まるコマンドを無視
setopt hist_verify            # ヒストリー展開後にコマンドを表示
setopt share_history          # ヒストリーデータを共有
setopt extended_history       # コマンドの開始時刻と実行時間を記録

# ヒストリーを完全に表示（実行時間を含む）
alias history="fc -li 1"

# エイリアスの設定

# ezaコマンドのエイリアス設定
alias ls="eza --icons"
alias ll="eza -l --icons"
alias la="eza -la --icons"
alias lt="eza --tree --icons --git-ignore"
alias lta="eza --tree --icons"
alias lmt='eza --tree --git-ignore --classify=always --no-user --no-time --no-filesize --color=never'
alias vim='nvim'

# ezaの補完を有効化
compdef _ls eza

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
    prompt_symbol=
    case "$PROMPT_ALTERNATIVE" in
        twoline)
            PROMPT=$'%F{%(#.red.green)}┌──[%B%F{%(#.red.blue)}%n${prompt_symbol}%m%b%F{%(#.red.green)}]─[%B%F{reset}%(6~.%-1~/…/%4~.%5~)%b%F{%(#.red.green)}]\n└─%B%(#.%F{red}#.%F{green}$)%b%F{reset} '
            ;;
        oneline)
            PROMPT=$'%F{green}%n${prompt_symbol}%m%f:%F{blue}%~%f%(#.#.$) '
            RPROMPT=
            ;;
        backtrack)
            PROMPT=$'%F{red}%n${prompt_symbol}%m%f:%F{blue}%~%f%(#.#.$) '
            RPROMPT=
            ;;
    esac
}

configure_prompt

# シンタックスハイライトのスタイル設定
ZSH_HIGHLIGHT_HIGHLIGHTERS=(main brackets pattern)
ZSH_HIGHLIGHT_STYLES[default]=none
ZSH_HIGHLIGHT_STYLES[unknown-token]=underline
ZSH_HIGHLIGHT_STYLES[reserved-word]=fg=cyan,bold

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

    if [ "$NEWLINE_BEFORE_PROMPT" = yes ] && [ -z "$ZSH_AUTOSUGGEST_BUFFER" ]; then
        if [ -z "$_NEW_LINE_BEFORE_PROMPT" ]; then
            _NEW_LINE_BEFORE_PROMPT=1
        else
            print ""
        fi
    fi
}

# zsh-autosuggestionsのハイライトスタイル
ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=#666'

# command-not-foundの有効化
if [ -f /etc/zsh_command_not_found ]; then
    . /etc/zsh_command_not_found
fi

# fpathの設定
fpath+=${ZDOTDIR:-~}/.zsh_functions

# ghq/fzf/eza 組み合わせ
function ghq-fzf_change_directory() {
    local src=$(ghq list | fzf --preview "eza -l -g -a --icons $(ghq root)/{} | tail -n+4 | awk '{print \$6\"/\"\$8\" \"\$9 \" \" \$10}'")
    if [ -n "$src" ]; then
        BUFFER="cd $(ghq root)/$src"
        zle accept-line
    fi
    zle -R -c
}

zle -N ghq-fzf_change_directory
bindkey '^f' ghq-fzf_change_directory

# Homebrewの設定
if [[ -d /opt/homebrew/bin ]]; then
    # Apple Silicon Mac
    export HOMEBREW_PREFIX="/opt/homebrew"
elif [[ -d /usr/local/bin/brew ]]; then
    # Intel Mac
    export HOMEBREW_PREFIX="/usr/local"
elif [[ -d /home/linuxbrew/.linuxbrew/bin ]]; then
    # Linux
    export HOMEBREW_PREFIX="/home/linuxbrew/.linuxbrew"
fi

if [[ -n "$HOMEBREW_PREFIX" && -f "$HOMEBREW_PREFIX/bin/brew" ]]; then
    export HOMEBREW_CELLAR="$HOMEBREW_PREFIX/Cellar"
    export HOMEBREW_REPOSITORY="$HOMEBREW_PREFIX/Homebrew"
    export PATH="$HOMEBREW_PREFIX/bin:$HOMEBREW_PREFIX/sbin:$PATH"
    export MANPATH="$HOMEBREW_PREFIX/share/man:${MANPATH:-}"
    export INFOPATH="$HOMEBREW_PREFIX/share/info:${INFOPATH:-}"
    
    # Homebrewの補完を有効化
    if type brew &>/dev/null; then
        FPATH="$HOMEBREW_PREFIX/share/zsh/site-functions:$FPATH"
    fi
fi

# 重複している設定を整理
# ASDFの設定（一度だけ読み込む）
if [[ -f "$HOME/.asdf/asdf.sh" ]]; then
    . "$HOME/.asdf/asdf.sh"
    . "$HOME/.asdf/completions/asdf.bash"
fi

# Goの設定
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin

snap_bin_path="/snap/bin"
if [ -n "${PATH##*${snap_bin_path}}" -a -n "${PATH##*${snap_bin_path}:*}" ]; then
    export PATH=$PATH:${snap_bin_path}
fi

# Cursor for AppImage
CURSOR_APPIMAGE_PATH="/opt/cursor.AppImage"
cursor() {
  # setsid で新しいセッションで起動し、標準入出力も閉じる
  # これによりターミナルとの関連を断ち切る
  setsid "${CURSOR_APPIMAGE_PATH}" --no-sandbox "$PWD" < /dev/null > /dev/null 2>&1 &

  # 念のため少し待つ (不要かもしれないが一応)
  # sleep 0.1
}

# クリップボード関連のエイリアス設定
if which pbcopy >/dev/null 2>&1 ; then 
    # Mac  
    alias -g C='| pbcopy'
elif which xsel >/dev/null 2>&1 ; then 
    # Linux
    alias pbcopy='xsel --clipboard --input'
    alias pbpaste='xsel --clipboard --output'
    alias -g C='| pbcopy'
elif which putclip >/dev/null 2>&1 ; then 
    # Cygwin 
    alias -g C='| putclip'
fi