-- 基本設定
vim.opt.encoding = 'utf-8'
vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.cursorline = true
vim.opt.mouse = 'a'
vim.opt.termguicolors = true
vim.opt.background = 'dark'
vim.opt.splitright = true
vim.opt.autoread = true
vim.api.nvim_create_autocmd('CursorHold', { command = 'checktime' })

-- インデント設定
vim.opt.expandtab = true
vim.opt.shiftwidth = 2
vim.opt.tabstop = 2
vim.opt.autoindent = true
vim.opt.smartindent = true

-- 表示設定
vim.opt.list = true
vim.opt.listchars = { tab = '»-', trail = '-', eol = '↲', extends = '»', precedes = '«', nbsp = '%' }
vim.opt.diffopt:append('iwhite')
vim.opt.laststatus = 3
vim.opt.showcmd = true
vim.opt.wildmenu = true
vim.opt.ruler = true
vim.opt.showmode = false
vim.opt.cmdheight = 1

-- 検索設定
vim.opt.ignorecase = true
vim.opt.smartcase = true
vim.opt.incsearch = true
vim.opt.hlsearch = true

-- クリップボード設定
vim.opt.clipboard = 'unnamedplus'

-- Lazy.nvimの設定
local lazypath = vim.fn.stdpath('data') .. '/lazy/lazy.nvim'
if not vim.loop.fs_stat(lazypath) then
  vim.fn.system({
    'git',
    'clone',
    '--filter=blob:none',
    'https://github.com/folke/lazy.nvim.git',
    lazypath,
  })
end
vim.opt.rtp:prepend(lazypath)

require('lazy').setup({
  -- カラースキーム
  { 'loctvl842/monokai-pro.nvim' },

  -- ファイルエクスプローラー
  { 'nvim-tree/nvim-tree.lua', dependencies = { 'nvim-tree/nvim-web-devicons' } },

  -- ステータスライン
  { 'nvim-lualine/lualine.nvim' },

  -- Git統合
  { 'tpope/vim-fugitive' },
  { 'lewis6991/gitsigns.nvim' },
  { 'sindrets/diffview.nvim' },

  -- ファジーファインダー
  { 'nvim-telescope/telescope.nvim', dependencies = { 'nvim-lua/plenary.nvim' } },

  -- LSPと自動補完
  { 'neovim/nvim-lspconfig' },
  { 'hrsh7th/nvim-cmp' },
  { 'hrsh7th/cmp-nvim-lsp' },
  { 'hrsh7th/cmp-buffer' },
  { 'hrsh7th/cmp-path' },
  { 'L3MON4D3/LuaSnip' },
  { 'saadparwaiz1/cmp_luasnip' },

  -- シンタックスハイライト
  { 'nvim-treesitter/nvim-treesitter', build = ':TSUpdate' },

  -- コメントアウト
  { 'tpope/vim-commentary' },

  -- 括弧補完
  { 'tpope/vim-surround' },

  -- インデントガイド (indent-blankline.nvim バージョン3)
  { 'lukas-reineke/indent-blankline.nvim' },

  -- カラーコードのハイライト
  { 'norcalli/nvim-colorizer.lua' },

  -- アイコン表示
  { 'onsails/lspkind-nvim' },

  -- Copilotの設定
  {
    "zbirenbaum/copilot.lua",
    event = "VeryLazy",
    config = function()
      require("copilot").setup({
        suggestion = { enabled = true },
        panel = { enabled = true },
        filetypes = {
          lua = true,
          python = true,
          javascript = true,
          typescript = true,
          ['*'] = true,
        },
      })
    end,
  },

  -- Copilot-cmpの設定
  {
    "zbirenbaum/copilot-cmp",
    dependencies = { "zbirenbaum/copilot.lua" },
    config = function()
      require("copilot_cmp").setup()
    end,
  }
})

-- カラースキーム設定
vim.cmd('colorscheme monokai-pro')

-- lualine設定
require('lualine').setup({
  options = {
    theme = 'monokai-pro',
    icons_enabled = true,
    globalstatus = true,
  },
})

-- diffview設定
require('diffview').setup({})

-- nvim-tree設定
require('nvim-tree').setup({
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
          unstaged = '✗',
          staged = '✓',
          unmerged = '',
          renamed = '➜',
          untracked = '★',
          deleted = '',
          ignored = '◌',
        },
      },
    },
  },
  filters = {
    dotfiles = false,
  },
  update_focused_file = {
    enable = true,
    update_cwd = true,
    ignore_list = {},
  },
})

-- nvim-treeのキーマッピング
vim.keymap.set('n', '<C-n>', ':NvimTreeToggle<CR>', { noremap = true, silent = true })

-- diffviewのキーマッピング
vim.keymap.set('n', '<C-d>', ':DiffviewOpen<CR>', { noremap = true, silent = true })

-- gitsigns設定
require('gitsigns').setup()

-- Telescope設定
vim.keymap.set('n', '<C-p>', ':Telescope find_files<CR>', { noremap = true, silent = true })
vim.keymap.set('n', '<C-f>', ':Telescope live_grep<CR>', { noremap = true, silent = true })

-- LSP設定
local nvim_lsp = require('lspconfig')

nvim_lsp.ts_ls.setup({})   -- tsserverからts_lsに変更
nvim_lsp.pyright.setup({})

-- 自動補完の設定
local cmp = require('cmp')
local luasnip = require('luasnip')
local lspkind = require('lspkind')

-- has_words_before関数を定義
local has_words_before = function()
  local line, col = unpack(vim.api.nvim_win_get_cursor(0))
  return col ~= 0 and
    vim.api.nvim_buf_get_lines(0, line - 1, line, true)[1]:sub(col, col):match("%s") == nil
end

cmp.setup({
  snippet = {
    expand = function(args)
      luasnip.lsp_expand(args.body)
    end,
  },
  mapping = cmp.mapping.preset.insert({
    ['<C-b>']   = cmp.mapping.scroll_docs(-4),
    ['<C-f>']   = cmp.mapping.scroll_docs(4),
    ['<C-Space>'] = cmp.mapping.complete(),
    ['<C-e>']   = cmp.mapping.abort(),
    ['<CR>']    = cmp.mapping.confirm({ select = true }),
    ["<Tab>"] = cmp.mapping(function(fallback)
      if cmp.visible() then
        cmp.select_next_item()
      elseif has_words_before() then
        cmp.complete()
      else
        fallback()
      end
    end, { "i", "s" }),
  }),
  sources = cmp.config.sources({
    { name = 'copilot',  max_item_count = 3 }, -- 優先度を上げる
    { name = 'nvim_lsp', max_item_count = 15, keyword_length = 2 },
    { name = 'luasnip',  max_item_count = 15, keyword_length = 2 },
    { name = 'buffer',   max_item_count = 15, keyword_length = 2 },
  }),
  formatting = {
    format = lspkind.cmp_format({
      mode = "symbol",
      maxwidth = 50,
      ellipsis_char = "...",
      symbol_map = { Copilot = "" },
    }),
  },
})

-- Treesitter設定
require('nvim-treesitter.configs').setup({
  ensure_installed = { 'c', 'cpp', 'python', 'javascript', 'typescript', 'lua' },
  highlight = {
    enable = true,
  },
})

-- indent-blankline設定 (バージョン3に対応)
require('ibl').setup({
  indent = {
    char = '│',
  },
  exclude = {
    filetypes = { 'help', 'terminal' },
  },
})

-- カラーコードのハイライト設定
require('colorizer').setup()

-- コメントアウトのキーマッピング
vim.keymap.set('n', '<C-/>', 'gcc', { noremap = false, silent = true })
vim.keymap.set('v', '<C-/>', 'gc', { noremap = false, silent = true })
