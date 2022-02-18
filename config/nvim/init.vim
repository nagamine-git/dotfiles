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
set list              "リストを表示
set listchars=tab:»-,trail:-,eol:↲,extends:»,precedes:«,nbsp:% "タブを表示する
set encoding=utf-8    "文字コードをUTF-8にする
set diffopt=iwhite

call plug#begin()
  Plug 'tpope/vim-fugitive' "git の vim 拡張
  Plug 'APZelos/blamer.nvim' "blamer の vim 拡張
  Plug 'airblade/vim-gitgutter' "git の vim 拡張
  Plug 'scrooloose/nerdtree' "ツリー表示
  Plug 'Xuyuanp/nerdtree-git-plugin' "git のツリー表示
  Plug 'ryanoasis/vim-devicons' "ファイルのアイコン表示
  Plug 'tpope/vim-repeat' "リピート
  Plug 'tpope/vim-commentary' "複数行コメントアウト
  Plug 'vim-airline/vim-airline' "vim-airline を使用する
  Plug 'vim-airline/vim-airline-themes' "vim-airline を使用する
  Plug 'nvim-treesitter/nvim-treesitter'  "シンタックスハイライト
  Plug 'sheerun/vim-polyglot' "シンタックスハイライト
  Plug 'pangloss/vim-javascript' "JavaScript
  Plug 'leafgarland/typescript-vim' "TypeScript
  Plug 'tomasr/molokai' "Molokai
  Plug 'cormacrelf/vim-colors-github'
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
  Plug 'neoclide/coc.nvim', {'branch': 'release'} "補完機能
  Plug 'dense-analysis/ale' "非同期静的解析
  Plug 'edkolev/tmuxline.vim' "tmuxline
  Plug 'brooth/far.vim' "置換を楽に
  Plug 'prabirshrestha/async.vim' "非同期処理
  Plug 'glidenote/memolist.vim'
  Plug 'Quramy/tsuquyomi', { 'do': 'npm -g install typescript' }
  Plug 'Shougo/vimproc.vim', { 'do': 'make' }
call plug#end()

" カラースキーム
set termguicolors
let g:rehash256 = 1
let g:airline_powerline_fonts = 1
if &diff
  colorscheme github
  let g:airline_theme = "github"
  let g:lightline = { 'colorscheme': 'github' }
  let g:gitgutter_highlight_lines = 0 "git のハイライト
else
  let g:airline_theme = 'molokai'
  colorscheme molokai
  let g:gitgutter_highlight_lines = 1 "git のハイライト
endif

let g:ctrlp_use_caching = 0 " ctrlpでキャッシュを使わない

let g:ctrlp_map = '<c-p>' "ファイル検索
let g:ctrlp_cmd = 'CtrlP' "ファイル検索
let g:ctrlp_user_command = ['.git', 'cd %s && git ls-files -co --exclude-standard']

" CtrlSFの設定
nmap     <C-F>f <Plug>CtrlSFPrompt
vmap     <C-F>f <Plug>CtrlSFVwordPath
vmap     <C-F>F <Plug>CtrlSFVwordExec
nmap     <C-F>n <Plug>CtrlSFCwordPath
nmap     <C-F>p <Plug>CtrlSFPwordPath
nnoremap <C-F>o :CtrlSFOpen<CR>
nnoremap <C-F>t :CtrlSFToggle<CR>
inoremap <C-F>t <Esc>:CtrlSFToggle<CR>
let g:ctrlsf_search_mode = 'async'
let g:ctrlsf_auto_focus = {
    \ "at": "start"
    \ }
let g:ctrlsf_default_view_mode = 'compact'

let g:jsx_ext_required = 1 " jsx
let g:blamer_enabled = 1

let g:indent_guides_enable_on_vim_startup = 1
let NERDTreeShowHidden = 1 "隠しファイルもtreeに表示
let g:ctrlp_custom_ignore = 'node_modules\|DS_Store\|git'
