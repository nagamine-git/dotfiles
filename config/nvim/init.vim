" 基本設定
set number
set relativenumber
set expandtab
set shiftwidth=2
set tabstop=2
set autoindent
set smartindent
set cursorline
set termguicolors
set background=dark
set mouse=a
set splitright
set clipboard=unnamedplus
set encoding=utf-8
set list
set listchars=tab:»-,trail:-,eol:↲,extends:»,precedes:«,nbsp:%
set diffopt=iwhite
set autoread
autocmd CursorHold * checktime

" 検索設定
set ignorecase
set smartcase
set incsearch
set hlsearch

" 表示設定
set laststatus=2
set showcmd
set wildmenu
set ruler

" プラグイン管理
call plug#begin('~/.config/nvim/plugged')

" カラースキーム
Plug 'loctvl842/monokai-pro.nvim'

" ファイルエクスプローラー
Plug 'nvim-tree/nvim-tree.lua'
Plug 'nvim-tree/nvim-web-devicons'

" ステータスライン
Plug 'nvim-lualine/lualine.nvim'

" Git統合
Plug 'tpope/vim-fugitive'
Plug 'lewis6991/gitsigns.nvim'

" ファジーファインダー
Plug 'nvim-telescope/telescope.nvim'
Plug 'nvim-lua/plenary.nvim'

" LSPと自動補完
Plug 'neovim/nvim-lspconfig'
Plug 'hrsh7th/nvim-cmp'
Plug 'hrsh7th/cmp-nvim-lsp'
Plug 'hrsh7th/cmp-buffer'
Plug 'hrsh7th/cmp-path'
Plug 'L3MON4D3/LuaSnip'
Plug 'saadparwaiz1/cmp_luasnip'

" シンタックスハイライト
Plug 'nvim-treesitter/nvim-treesitter', {'do': ':TSUpdate'}

" コメントアウト
Plug 'tpope/vim-commentary'

" 括弧補完
Plug 'tpope/vim-surround'

" インデントガイド
Plug 'lukas-reineke/indent-blankline.nvim'

" カラーコードのハイライト
Plug 'norcalli/nvim-colorizer.lua'

call plug#end()

" Vim Script
colorscheme monokai-pro

" lualine設定
lua << EOF
require('lualine').setup {
  options = {
    theme = 'codedark',
    icons_enabled = true,
    section_separators = '',
    component_separators = '',
  },
}
EOF

" nvim-tree設定
lua << EOF
require('nvim-tree').setup {
  view = {
    width = 30,
    side = 'left',
  },
  renderer = {
    icons = {
      show = {
        git = true,
        folder = true,
        file = true,
        folder_arrow = true,
      },
      glyphs = {
        default = '',
        symlink = '',
        folder = {
          arrow_open = '',
          arrow_closed = '',
          default = '',
          open = '',
          empty = '',
          empty_open = '',
          symlink = '',
          symlink_open = '',
        },
        git = {
          unstaged = "✗",
          staged = "✓",
          unmerged = "",
          renamed = "➜",
          untracked = "★",
          deleted = "",
          ignored = "◌"
        },
      },
    },
  },
  filters = {
    dotfiles = false,
    custom = { '.DS_Store' },
  },
}
EOF
nnoremap <C-n> :NvimTreeToggle<CR>

" gitsigns設定
lua << EOF
require('gitsigns').setup()
EOF

" Telescope設定
nnoremap <C-p> :Telescope find_files<CR>
nnoremap <C-f> :Telescope live_grep<CR>

" LSP設定
lua << EOF
local nvim_lsp = require('lspconfig')

-- TypeScript用サーバー名を更新
nvim_lsp.ts_ls.setup{}     -- JavaScript/TypeScript
nvim_lsp.pyright.setup{}   -- Python

-- 自動補完の設定
local cmp = require'cmp'
cmp.setup({
  snippet = {
    expand = function(args)
      require'luasnip'.lsp_expand(args.body)
    end,
  },
  mapping = cmp.mapping.preset.insert({
    ['<C-b>'] = cmp.mapping.scroll_docs(-4),
    ['<C-f>'] = cmp.mapping.scroll_docs(4),
    ['<C-Space>'] = cmp.mapping.complete(),
    ['<C-e>'] = cmp.mapping.abort(),
    ['<CR>'] = cmp.mapping.confirm({ select = true }),
  }),
  sources = cmp.config.sources({
    { name = 'nvim_lsp' },
    { name = 'luasnip' },
  }, {
    { name = 'buffer' },
  })
})
EOF

" Treesitter設定
lua << EOF
require('nvim-treesitter.configs').setup {
  ensure_installed = { "c", "cpp", "python", "javascript", "typescript", "lua" },
  highlight = {
    enable = true,
    additional_vim_regex_highlighting = false,
  },
}
EOF

" indent-blankline設定（バージョン3対応）
lua << EOF
require("ibl").setup {
  indent = { char = "│" },
  exclude = {
    filetypes = {"help", "terminal"},
    buftypes = {"terminal"},
  },
}
EOF

" カラーコードのハイライト設定
lua << EOF
require'colorizer'.setup()
EOF

" その他の設定
set diffopt+=iwhite
syntax on

" キーバインド設定
nmap <C-/> gcc
vmap <C-/> gc

" カラー設定
highlight Comment ctermfg=LightBlue guifg=LightBlue

" 行末の空白をハイライト
highlight ExtraWhitespace ctermbg=red guibg=red
autocmd BufWinEnter * match ExtraWhitespace /\s\+$/
autocmd InsertEnter * match ExtraWhitespace /\s\+\%#\@<!$/
autocmd InsertLeave * match ExtraWhitespace /\s\+$/
autocmd BufWinLeave * call clearmatches()
