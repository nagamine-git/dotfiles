#!/usr/bin/env bash

# 未定義な変数があったら途中で終了する
set -u

# dotfilesディレクトリに移動する
BASEDIR=$(pwd)
cd $BASEDIR

# 必要なディレクトリの作成
mkdir -p ${HOME}/.config
mkdir -p ${HOME}/.local/share/fonts

# ファイルディレクトリの作成確認
mkdir -p ${BASEDIR}/files

ln -snfv $BASEDIR/config ${HOME}/.config

# その他の設定ファイル
ln -snfv $BASEDIR/dot.tmux.conf ${HOME}/.tmux.conf
ln -snfv $BASEDIR/dot.zshrc ${HOME}/.zshrc
ln -snfv $BASEDIR/dot.gitconfig ${HOME}/.gitconfig

# 必要なパッケージのインストール
sudo apt update
sudo apt install -y \
    zsh \
    tmux \
    git \
    curl \
    wget \
    ripgrep \
    fzf \
    bat \
    python3-pip \
    python3-venv \
    build-essential \
    golang-go \
    ca-certificates \
    gnupg \
    lsb-release \
    unzip \
    wget \
    apt-transport-https \
    software-properties-common

# Neovim 0.8.0以上を直接ダウンロード&インストール
curl -LO https://github.com/neovim/neovim/releases/latest/download/nvim-linux-x86_64.tar.gz
sudo rm -rf /opt/nvim
sudo mkdir -p /opt/nvim
sudo tar -C /opt/nvim -xzf nvim-linux-x86_64.tar.gz --strip-components=1
sudo ln -sf /opt/nvim/bin/nvim /usr/local/bin/nvim
rm nvim-linux-x86_64.tar.gz

# 日本語ロケールの設定（VSCode用）
echo "日本語ロケールを設定中..."
if ! locale -a | grep -q ja_JP.UTF-8; then
  sudo apt-get install -y locales
  sudo sed -i 's/^# *\(ja_JP.UTF-8\)/\1/' /etc/locale.gen
  sudo locale-gen
  echo "日本語ロケールの設定が完了しました"
else
  echo "日本語ロケールは既に設定されています"
fi

# フォントをインストール中...
echo "プログラミングフォントをインストール中..."
# Noto Sans CJK JP のインストール
sudo apt install -y fonts-noto-cjk

# プログラミングフォントのインストール（HackGen、PlemolJP、UDEV Gothic、Firge）
# 1. HackGen のインストール
sudo mkdir -p /usr/share/fonts/HackGen
HACKGEN_VERSION=$(curl -sL https://api.github.com/repos/yuru7/HackGen/releases/latest | grep -oP '"tag_name": "\K(.*)(?=")')
echo "HackGen の最新バージョン: ${HACKGEN_VERSION} をダウンロードします"
wget https://github.com/yuru7/HackGen/releases/download/${HACKGEN_VERSION}/HackGen_NF_${HACKGEN_VERSION}.zip
sudo unzip HackGen_NF_${HACKGEN_VERSION}.zip -d /usr/share/fonts/HackGen
rm HackGen_NF_${HACKGEN_VERSION}.zip

# 2. PlemolJP のインストール
sudo mkdir -p /usr/share/fonts/PlemolJP
PLEMOLJP_VERSION=$(curl -sL https://api.github.com/repos/yuru7/PlemolJP/releases/latest | grep -oP '"tag_name": "\K(.*)(?=")')
echo "PlemolJP の最新バージョン: ${PLEMOLJP_VERSION} をダウンロードします"
wget https://github.com/yuru7/PlemolJP/releases/download/${PLEMOLJP_VERSION}/PlemolJP_NF_${PLEMOLJP_VERSION}.zip
sudo unzip PlemolJP_NF_${PLEMOLJP_VERSION}.zip -d /usr/share/fonts/PlemolJP
rm PlemolJP_NF_${PLEMOLJP_VERSION}.zip

# 3. UDEV Gothic のインストール
sudo mkdir -p /usr/share/fonts/UDEVGothic
UDEV_VERSION=$(curl -sL https://api.github.com/repos/yuru7/udev-gothic/releases/latest | grep -oP '"tag_name": "\K(.*)(?=")')
echo "UDEV Gothic の最新バージョン: ${UDEV_VERSION} をダウンロードします"
wget https://github.com/yuru7/udev-gothic/releases/download/${UDEV_VERSION}/UDEVGothic_NF_${UDEV_VERSION}.zip
sudo unzip UDEVGothic_NF_${UDEV_VERSION}.zip -d /usr/share/fonts/UDEVGothic
rm UDEVGothic_NF_${UDEV_VERSION}.zip

# 4. Firge のインストール
sudo mkdir -p /usr/share/fonts/Firge
FIRGE_VERSION=$(curl -sL https://api.github.com/repos/yuru7/Firge/releases/latest | grep -oP '"tag_name": "\K(.*)(?=")')
echo "Firge の最新バージョン: ${FIRGE_VERSION} をダウンロードします"
wget https://github.com/yuru7/Firge/releases/download/${FIRGE_VERSION}/FirgeNerd_${FIRGE_VERSION}.zip
sudo unzip FirgeNerd_${FIRGE_VERSION}.zip -d /usr/share/fonts/Firge
rm FirgeNerd_${FIRGE_VERSION}.zip

# 5. RobotoNotoSansJP のインストール
echo "RobotoNotoSansJP フォントをインストール中..."
sudo mkdir -p /usr/share/fonts/RobotoNotoSansJP
# 各ウェイトのフォントをダウンロード
ROBOTO_BASE_URL="https://raw.githubusercontent.com/reindex-ot/RobotoNotoSansJP/main"
ROBOTO_WEIGHTS=("Black" "Bold" "Light" "Medium" "Regular" "Thin")

for weight in "${ROBOTO_WEIGHTS[@]}"; do
  echo "Roboto-NotoSansJP-${weight}.ttf をダウンロード中..."
  sudo wget -q "${ROBOTO_BASE_URL}/Roboto-NotoSansJP-${weight}.ttf" -O "/usr/share/fonts/RobotoNotoSansJP/Roboto-NotoSansJP-${weight}.ttf"
done

# フォントキャッシュの更新
sudo fc-cache -f -v
echo "RobotoNotoSansJPフォントのインストールが完了しました"

# Firefoxが適切に日本語フォントを表示するための設定
echo "Firefoxの日本語フォント設定をセットアップ中..."
sudo mkdir -p /etc/fonts
sudo tee /etc/fonts/local.conf > /dev/null << 'EOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
    <alias>
        <family>serif</family>
        <prefer>
            <family>Roboto</family>
            <family>Noto Sans JP</family>
            <family>Noto Serif</family>
        </prefer>
    </alias>
    <alias>
        <family>sans-serif</family>
        <prefer>
            <family>Roboto</family>
            <family>Noto Sans JP</family>
        </prefer>
    </alias>
    <alias>
        <family>monospace</family>
        <prefer>
            <family>Firge35Nerd Console</family>
            <family>Firge</family>
        </prefer>
    </alias>
</fontconfig>
EOF
sudo fc-cache -f -v
echo "Firefoxのフォント設定が完了しました"

# フォントのレンダリング設定を調整
echo "フォントレンダリング設定を調整中..."
sudo mkdir -p /etc/fonts/conf.d
sudo tee /etc/fonts/conf.d/10-hinting-none.conf > /dev/null << 'EOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <match target="font">
    <edit name="hintstyle" mode="assign">
      <const>hintnone</const>
    </edit>
  </match>
</fontconfig>
EOF

sudo tee /etc/fonts/conf.d/11-lcdfilter-default.conf > /dev/null << 'EOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <match target="font">
    <edit name="lcdfilter" mode="assign">
      <const>lcddefault</const>
    </edit>
  </match>
</fontconfig>
EOF

sudo tee /etc/fonts/conf.d/12-subpixel-none.conf > /dev/null << 'EOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <match target="font">
    <edit name="rgba" mode="assign">
      <const>none</const>
    </edit>
  </match>
</fontconfig>
EOF

sudo fc-cache -f -v
echo "フォントレンダリング設定の調整が完了しました"

# Dockerのインストール
# Dockerの公式GPGキーを追加
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Dockerのリポジトリを追加
echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Dockerのインストール
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 現在のユーザーをdockerグループに追加
sudo usermod -aG docker $USER

# Oh My Zshのインストール
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended

# zshプラグインのインストール
git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autosuggestions
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting
git clone https://github.com/zsh-users/zsh-history-substring-search ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-history-substring-search

# ASDFのインストール
git clone https://github.com/asdf-vm/asdf.git ~/.asdf --branch v0.13.1
# GOPATHの設定（先に環境変数を設定）
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin

# GOPATHディレクトリの作成
mkdir -p $GOPATH/bin

# ghqのインストール（特定のバージョンを指定）
go install github.com/x-motemen/ghq@v1.4.0

# ghqの基本設定
git config --global ghq.root ~/ghq

# fusumaのインストールと設定
sudo gem install fusuma
sudo gem install fusuma-plugin-keypress
sudo gem install fusuma-plugin-sendkey

# fusumaの設定ファイルディレクトリを作成
sudo mkdir -p /root/.config/fusuma

# fusumaの設定ファイルをrootのディレクトリにコピー
sudo cp $BASEDIR/config/fusuma/config.yml /root/.config/fusuma/config.yml

# 必要なグループにユーザーを追加（入力デバイスへのアクセス権）
sudo usermod -aG input $USER

# fusumaのsystemdサービス設定
sudo cp $BASEDIR/files/fusuma.service /etc/systemd/system/fusuma.service
# ユーザー名を置換
sudo sed -i "s/%USER%/$USER/g" /etc/systemd/system/fusuma.service

# fusumaサービスの有効化と起動
sudo systemctl daemon-reload
sudo systemctl enable fusuma.service
sudo systemctl start fusuma.service

# XKBカスタム設定
# xcapeのインストール（先にインストールしておく）
sudo apt install -y xcape

# Xfce環境で必要なパッケージ確認
sudo apt install -y xserver-xorg-dev x11-xkb-utils x11-utils

# カスタムXKBシンボルファイルの作成
sudo mkdir -p /usr/share/X11/xkb/symbols/
sudo cp $BASEDIR/files/custom /usr/share/X11/xkb/symbols/custom

# 設定を適用するスクリプトの作成
sudo cp $BASEDIR/files/apply-custom-xkb /usr/local/bin/apply-custom-xkb
sudo chmod +x /usr/local/bin/apply-custom-xkb

# Xfce向け自動起動設定
mkdir -p ~/.config/autostart
cp $BASEDIR/files/custom-xkb.desktop ~/.config/autostart/custom-xkb.desktop

# Xfceのキーボード設定に影響を与えないようにするため、既存の設定をバックアップ
if [ -f ~/.config/xfce4/xfconf/xfce-perchannel-xml/keyboard-layout.xml ]; then
    cp ~/.config/xfce4/xfconf/xfce-perchannel-xml/keyboard-layout.xml ~/.config/xfce4/xfconf/xfce-perchannel-xml/keyboard-layout.xml.bak
fi

# 今すぐ適用して動作確認
echo "カスタムキーボード設定を適用中..."
/usr/local/bin/apply-custom-xkb
if [ $? -eq 0 ]; then
    echo "キーボード設定の適用に成功しました"
else
    echo "キーボード設定の適用中にエラーが発生しました。$HOME/.xkb_setup.logを確認してください"
fi

# デフォルトシェルをzshに変更
sudo chsh -s $(which zsh)

# フォントキャッシュの更新
fc-cache -f -v

# GitHubのSSH設定
git config --global url."git@github.com:".insteadOf "https://github.com/"

# ezaのインストール
sudo mkdir -p /etc/apt/keyrings
wget -qO- https://raw.githubusercontent.com/eza-community/eza/main/deb.asc | sudo gpg --dearmor -o /etc/apt/keyrings/gierens.gpg
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/gierens.gpg] http://deb.gierens.de stable main" | sudo tee /etc/apt/sources.list.d/gierens.list
sudo chmod 644 /etc/apt/keyrings/gierens.gpg /etc/apt/sources.list.d/gierens.list
sudo apt update
sudo apt install -y eza

echo "セットアップが完了しました。"
echo "ターミナルを再起動して、新しい設定を反映させてください。"
echo "Dockerを使用するには、一度ログアウトして再ログインする必要があります。"

