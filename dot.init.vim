set number             "行番号を表示
set expandtab          "タブ入力を空白に変換
set hlsearch           "検索した文字をハイライトする
set ignorecase         "大文字小文字を区別しない
set incsearch          "検索時にインクリメンタルサーチを有効にする
set smartcase          "小文字で検索した場合は、大文字小文字の違いは無視、大文字を含む文字列で検索した場合は無視しない
set laststatus=2       "最終行の行番号を表示
syntax on              "言語指定
set autoindent         "改行時に自動でインデントする
set showcmd            ":!コマンドを表示
set background=dark    "背景色を暗くする
set wildmenu           "ワイルドカードを使用できるようにする
set ruler              "行番号を表示
set cursorline         "カーソル行をハイライト
set number             "行番号を表示
set tabstop=2          "タブを何文字の空白に変換するか
set shiftwidth=2       "自動インデント時に入力する空白の数
set splitright         "画面を縦分割する際に右に開く
set clipboard=unnamed  "yank した文字列をクリップボードにコピー
set autoread           "ファイルを開いたときに自動で読み込む
set mouse=a            "マウス使用許可

call plug#begin()
  Plug 'tpope/vim-fugitive' "git の vim 拡張
  Plug 'airblade/vim-gitgutter' "git の vim 拡張
  Plug 'scrooloose/nerdtree' "ツリー表示
  Plug 'ryanoasis/vim-devicons' "ファイルのアイコン表示
  Plug 'junegunn/fzf', { 'do': { -> fzf#install() } } "fzf を使用する
  Plug 'junegunn/fzf.vim' "fzf を使用する
  Plug 'tpope/vim-repeat' "リピート
  Plug 'tpope/vim-commentary' "複数行コメントアウト
  Plug 'vim-airline/vim-airline' "vim-airline を使用する
  Plug 'vim-airline/vim-airline-themes' "vim-airline を使用する
  Plug 'nvim-treesitter/nvim-treesitter', {'do': ':TSUpdate'}  "シンタックスハイライト
  Plug 'sheerun/vim-polyglot' "シンタックスハイライト
  Plug 'pangloss/vim-javascript' "JavaScript
  Plug 'leafgarland/typescript-vim' "TypeScript
  Plug 'tomasr/molokai' "Molokai
  Plug 'tpope/vim-rails' "Rails
  Plug 'tpope/vim-surround' "括弧補完
  Plug 'ctrlpvim/ctrlp.vim' "検索
  Plug 'mxw/vim-jsx' "JSX
  Plug 'leafgarland/typescript-vim' "TypeScript
  Plug 'peitalin/vim-jsx-typescript' "TypeScript
  Plug 'bronson/vim-trailing-whitespace' "行末の空白をハイライト
  Plug 'nathanaelkane/vim-indent-guides' "インデントガイド
  Plug 'vim-scripts/AnsiEsc.vim' "色付け
  Plug 'rking/ag.vim' "ag
  Plug 'dyng/ctrlsf.vim' "非同期ファイル検索
call plug#end()

" カラースキーム
colorscheme molokai
let g:rehash256 = 1

let g:ctrlp_clear_cache_on_exit = 0 " ctrlpで終了時にャッシュを残す
let g:ctrlp_use_caching = 1 " ctrlpで終了時にャッシュを残す

let g:ctrlp_map = '<c-p>' "検索
let g:ctrlp_cmd = 'CtrlP' "検索

let g:jsx_ext_required = 1 " jsx
let g:gitgutter_highlight_lines = 1 "git のハイライト

let g:indent_guides_enable_on_vim_startup = 1

