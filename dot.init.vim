set number             "行番号を表示
set autoindent         "改行時に自動でインデントする
set tabstop=2          "タブを何文字の空白に変換するか
set shiftwidth=2       "自動インデント時に入力する空白の数
set expandtab          "タブ入力を空白に変換
set splitright         "画面を縦分割する際に右に開く
set clipboard=unnamed  "yank した文字列をクリップボードにコピー
set hls                "検索した文字をハイライトする
set ignorecase         "大文字小文字を区別しない
set nocompatible       "vim の互換機能を使用しない
set autoread           "ファイルを開いたときに自動で読み込む 

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
  Plug 'fatih/molokai' "Molokai
  Plug 'tpope/vim-rails' "Rails
  Plug 'tpope/vim-surround' "括弧補完
  Plug 'ctrlpvim/ctrlp.vim' "検索
  Plug 'mxw/vim-jsx' "JSX
  Plug 'leafgarland/typescript-vim' "TypeScript
  Plug 'peitalin/vim-jsx-typescript' "TypeScript
call plug#end()

colorscheme molokai
let g:rehash256 = 1

let g:ctrlp_clear_cache_on_exit = 0 " ctrlpで終了時にャッシュを残す
let g:ctrlp_use_caching = 1 " ctrlpで終了時にャッシュを残す

let g:ctrlp_map = '<c-p>' "検索
let g:ctrlp_cmd = 'CtrlP' "検索

let g:jsx_ext_required = 1 " jsx
let g:gitgutter_highlight_lines = 1 "git のハイライト
