# dotfiles

個人的な設定ファイルを[chezmoi](https://www.chezmoi.io/)で管理するリポジトリです。
主にEndeavourOS（Archベース）向けに最適化されています。

## 主な設定

- ディストリビューション: EndeavourOS / Arch Linux
- シェル: Zsh + Starship
- ウィンドウマネージャ: Hyprland
- ターミナル: foot
- エディタ: Neovim
- 入力メソッド: fcitx5
- システム最適化: irqbalance, powertop
- 開発ツール: Docker, lazygit, lazydocker, atuin
- その他: git, SSH, waybar など

## 使い方

### インストール

```bash
# chezmoiのインストール
paru -S chezmoi

# リポジトリの取得と適用
chezmoi init --apply nagamine-git
```

### 更新

```bash
# 変更を適用
chezmoi apply -v
```

### パッケージ

必要なパッケージは `pkglist.txt` に記載されており、`run_onchange_setup.sh` 実行時に自動的にインストールされます。

### tuigreet
/etc/greetd/config.toml
```bash
[terminal]
vt = 1

[default_session]
# command = "tuigreet -t -r --remember-session --asterisks --cmd hyprland"
command = "agreety -c hyprland"
user    = "tsuyoshi"
```