-- init.lua
vim.loader.enable()

-- 基本設定
vim.opt.encoding = 'utf-8'
vim.opt.number = true
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
vim.opt.diffopt:append('iwhite,iwhiteall,iblank')
vim.opt.laststatus = 3 -- Global statusline (recommended for avante.nvim)
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

-- GPG設定
vim.g.GPGDefaultRecipients = {}      -- 既定受信者なし
vim.g.GPGPossibleRecipients = {}     -- 候補リストなし
vim.g.GPGPreferSymmetric = 1         -- 新規は対称（パスワード

-- Lazy.nvimの設定
local lazypath = vim.fn.stdpath('data') .. '/lazy/lazy.nvim'
if not vim.loop.fs_stat(lazypath) then
  vim.fn.system({
    'git',
    'clone',
    '--filter=blob:none',
    'https://github.com/folke/lazy.nvim.git',
    '--branch=stable', -- latest stable release
    lazypath,
  })
end
vim.opt.rtp:prepend(lazypath)

require('lazy').setup({
  -- カラースキーム
  { 'folke/tokyonight.nvim' },

  -- ファイルエクスプローラー
  { 'nvim-tree/nvim-tree.lua', dependencies = { 'nvim-tree/nvim-web-devicons' } },

  -- ステータスライン
  { 'nvim-lualine/lualine.nvim', dependencies = { 'nvim-tree/nvim-web-devicons' } },

  -- Git統合
  { 'lewis6991/gitsigns.nvim' },
  { 'tpope/vim-fugitive' },
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
  { 'numToStr/Comment.nvim' },

  -- 括弧補完
  { 'windwp/nvim-autopairs' },

  -- インデントガイド
  { 'lukas-reineke/indent-blankline.nvim', main = "ibl" },

  -- アイコン表示
  { 'onsails/lspkind-nvim' },

  -- 暗号化
  { 'jamessan/vim-gnupg' },

  -- Claude Code
  {
    "greggh/claude-code.nvim",
    dependencies = {
      "nvim-lua/plenary.nvim", -- Required for git operations
    },
    config = function()
      require("claude-code").setup({
        window = {
          position = "vertical",
          split_ratio = 0.3,
          enter_insert = true,
        }
      })
    end
  }  
})

-- カラースキーム設定
vim.cmd('colorscheme tokyonight-night')

-- lualine設定
require('lualine').setup({
  options = {
    theme = 'nord',
    icons_enabled = true,
    globalstatus = true,
  },
})

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
    },
  },
  filters = {
    dotfiles = false,
  },
  update_focused_file = {
    enable = true,
    update_cwd = true,
  },
})

-- nvim-treeのキーマッピング
vim.keymap.set('n', '<C-n>', ':NvimTreeToggle<CR>', { noremap = true, silent = true })

-- gitsigns設定
require('gitsigns').setup()

-- Telescope設定
vim.keymap.set('n', '<C-p>', ':Telescope find_files<CR>', { noremap = true, silent = true })
vim.keymap.set('n', '<C-f>', ':Telescope live_grep<CR>', { noremap = true, silent = true })

-- Diffview設定
require('diffview').setup({
  diff_binaries = false,
  enhanced_diff_hl = true,
  use_icons = true,
})

-- 通常のvim diff用のカスタム色設定
local function set_base_diff_colors()
  vim.api.nvim_set_hl(0, 'DiffAdd', { bg = '#003800', fg = '#ffffff' })
  vim.api.nvim_set_hl(0, 'DiffDelete', { bg = '#880000', fg = '#ffffff' })
  vim.api.nvim_set_hl(0, 'DiffText', { bg = '#003800', fg = '#ffffff' })
  vim.api.nvim_set_hl(0, 'DiffChange', { bg = '#880000', fg = '#ffffff' })
end

set_base_diff_colors()
vim.api.nvim_create_autocmd('ColorScheme', { callback = set_base_diff_colors })

vim.keymap.set('n', '<C-d>', ':DiffviewOpen<CR>', { noremap = true, silent = true })
vim.keymap.set('n', '<leader>dc', ':DiffviewClose<CR>', { noremap = true, silent = true })

-- LSP設定
local lspconfig = require('lspconfig')

-- 自動補完の設定
local cmp = require('cmp')
local luasnip = require('luasnip')
local lspkind = require('lspkind')

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
    ['<C-b>'] = cmp.mapping.scroll_docs(-4),
    ['<C-f>'] = cmp.mapping.scroll_docs(4),
    ['<C-Space>'] = cmp.mapping.complete(),
    ['<C-e>'] = cmp.mapping.abort(),
    ['<CR>'] = cmp.mapping.confirm({ select = true }),
    ["<Tab>"] = cmp.mapping(function(fallback)
      if cmp.visible() then
        cmp.select_next_item()
      elseif luasnip.expand_or_jumpable() then
        luasnip.expand_or_jump()
      elseif has_words_before() then
        cmp.complete()
      else
        fallback()
      end
    end, { "i", "s" }),
    ["<S-Tab>"] = cmp.mapping(function(fallback)
      if cmp.visible() then
        cmp.select_prev_item()
      elseif luasnip.jumpable(-1) then
        luasnip.jump(-1)
      else
        fallback()
      end
    end, { "i", "s" }),
  }),
  sources = cmp.config.sources({
    { name = 'nvim_lsp', max_item_count = 15, keyword_length = 2 },
    { name = 'luasnip', max_item_count = 15, keyword_length = 2 },
    { name = 'buffer', max_item_count = 15, keyword_length = 2 },
    { name = 'path' },
  }),
  formatting = {
    format = lspkind.cmp_format({
      mode = "symbol",
      maxwidth = 50,
      ellipsis_char = "...",
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

-- indent-blankline設定
require('ibl').setup()

-- Comment.nvim設定
require('Comment').setup()

-- nvim-autopairs設定
require('nvim-autopairs').setup()

-- Avanteのキーマッピング
vim.keymap.set('n', '<leader>aa', function() require('avante').toggle() end, { desc = "avante: toggle sidebar" })
vim.keymap.set('n', '<leader>at', function() require('avante').toggle() end, { desc = "avante: toggle sidebar" })
vim.keymap.set('n', '<leader>ar', function() require('avante').refresh() end, { desc = "avante: refresh" })
vim.keymap.set('n', '<leader>af', function() require('avante').focus() end, { desc = "avante: focus" })
vim.keymap.set('n', '<leader>a?', function() require('avante').switch_provider() end, { desc = "avante: switch provider" })
vim.keymap.set('n', '<leader>ae', function() require('avante').edit() end, { desc = "avante: edit" })
vim.keymap.set('n', '<leader>aS', function() require('avante').stop() end, { desc = "avante: stop" })
vim.keymap.set('n', '<leader>ah', function() require('avante').history() end, { desc = "avante: history" })
