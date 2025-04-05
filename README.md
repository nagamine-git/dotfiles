# シンプルクロスプラットフォーム対応dotfiles

Mac/Linux間で共通の開発環境を[chezmoi](https://www.chezmoi.io/)で管理するdotfilesです。

## セットアップ

```bash
# 1. chezmoiインストール
sh -c "$(curl -fsLS get.chezmoi.io)" -- -b $HOME/.local/bin
export PATH="$HOME/.local/bin:$PATH"

# 2. dotfilesの初期化と適用
chezmoi init https://github.com/nagamine-git/dotfiles.git
chezmoi apply -v

# 3. 環境別セットアップの実行
chezmoi cd
bash .chezmoitemplates/$(uname | tr '[:upper:]' '[:lower:]').tmpl
```

## 機能概要

### Mac環境
- **基本ツール**: Homebrew経由で開発ツールとフォントをインストール
- **キーボード**: Karabinerで親指センサー機能とVim風ナビゲーション（Alt+hjkl）
- **ターミナル**: Alacritty + Firge35Nerd Console + Starship

### Linux環境
- **基本ツール**: apt経由でzsh, tmux, git, 日本語入力などをインストール
- **テーマ**: Arc Theme、Papirus Icon（推奨壁紙: [雪山と星空](https://unsplash.com/photos/snow-mountain-under-stars-phIFdC6lA4E)）
- **キーボード**: XKBでCapsLock/Ctrl入替とVim風ナビゲーション
- **タッチパッド**: Fusumaでマルチタッチジェスチャー対応

## 日常操作

```bash
chezmoi update          # 最新の設定を取得・適用
chezmoi cd              # 設定ディレクトリを開く
chezmoi edit ~/.zshrc   # 設定ファイルを編集
chezmoi add ~/.config/newapp/config.yaml  # 設定追加
```

## 構成要素

- **シェル環境**: zsh + Oh-My-Zsh + Starship
- **開発ツール**: git, tmux, neovim
- **フォント**: Firge（プログラミング用日本語）、RobotoNotoSansJP（ハイブリッド）
- **テーマ(Linux)**: Arc Theme + Papirus Icon

## ディレクトリ構成

```
dotfiles/
├── .chezmoitemplates/     # 環境別セットアップスクリプト
├── bin_linux/             # Linuxのみのスクリプト
├── dot_config/            # 各種設定ファイル
│   ├── nvim/              # Neovim設定
│   ├── git/               # Git設定
│   ├── starship/          # Starship設定
│   ├── fusuma/            # タッチパッド設定（Linux）
│   ├── autostart_linux/   # 自動起動設定（Linux）
│   └── systemd_linux/     # Systemdサービス設定（Linux）
└── dot_local_share_linux/ # カスタムキーボード設定（Linux）
```

<details>
<summary>4l2loopbackを使ったDroidCam仮想カメラの設定方法</summary>

## うまくいく設定のまとめ

1. **正しいバージョンのインストール**:
   ```
   sudo apt install -t bookworm-backports v4l2loopback-dkms=0.13.2-1 v4l2loopback-utils=0.13.2-1
   ```

2. **モジュールのロード設定**:
   ```
   sudo modprobe -r v4l2loopback
   sudo modprobe v4l2loopback exclusive_caps=1 card_label="DroidCam Virtual Camera" video_nr=4 max_width=1280 max_height=720
   ```

3. **必要なパラメータ**:
   - `exclusive_caps=1`: 必須（カメラとして認識されるようにする）
   - `video_nr=4`: デバイス番号固定
   - `max_width=1280 max_height=720`: 初期解像度（動作確認済み）

4. **パーミッション設定**:
   ```
   sudo usermod -a -G video $USER  # ユーザーをvideoグループに追加
   echo 'KERNEL=="video[0-9]*", GROUP="video", MODE="0660"' | sudo tee /etc/udev/rules.d/83-v4l2loopback.rules
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

5. **設定ファイルの作成**:
   ```
   sudo bash -c 'cat > /etc/modprobe.d/v4l2loopback.conf << EOF
   options v4l2loopback exclusive_caps=1 card_label="DroidCam Virtual Camera" video_nr=4 max_width=1280 max_height=720
   EOF'
   ```

6. **フレームレート設定**:
   ```
   v4l2-ctl -d /dev/video4 -p 60
   ```

## 高画質設定（安定したら）

```
sudo modprobe -r v4l2loopback
sudo modprobe v4l2loopback exclusive_caps=1 card_label="DroidCam Virtual Camera" video_nr=4 max_width=1920 max_height=1080 max_buffers=32

sudo bash -c 'cat > /etc/modprobe.d/v4l2loopback.conf << EOF
options v4l2loopback exclusive_caps=1 card_label="DroidCam Virtual Camera" video_nr=4 max_width=1920 max_height=1080 max_buffers=32
EOF'

v4l2-ctl -d /dev/video4 -p 60
```

## トラブルシューティング
- 動作しない場合は、解像度を下げる（1280x720）
- `lsmod | grep v4l2` でモジュールが正しくロードされているか確認
- `v4l2-ctl --list-devices` でデバイスが正しく認識されているか確認
- `stat /dev/video4` でパーミッションを確認（グループが「video」になっているか）

重要なポイントは、正しいバージョン（0.13.2-1）、解像度設定、exclusive_caps=1パラメータの使用、そして適切なパーミッション設定です。

</details>
