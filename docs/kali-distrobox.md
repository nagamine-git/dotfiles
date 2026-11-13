# Kali (distrobox)

am5-itx などの Linux で、Kali Linux を distrobox のコンテナとして動かす手順のメモ (README から移した)。

## 初期セットアップ
```bash
sudo mkdir -p /etc/distrobox
echo "DBX_CONTAINER_HOME_PREFIX=$HOME/distrobox" | sudo tee /etc/distrobox/distrobox.conf
sudo usermod -aG docker $USER
sudo systemctl start docker
distrobox create --name kali --image docker.io/kalilinux/kali-rolling:latest --home ~/distrobox/kali --additional-flags "--privileged"
distrobox enter kali
export GTK_IM_MODULE=fcitx
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y kali-linux-large locales firefox-esr git dnsutils tor proxychains4
cp /etc/proxychains4.conf ~/.proxychains.conf
sudo systemctl enable tor
```

check ip and tor
```bash
curl -s https://httpbin.org/ip
curl -s https://check.torproject.org/api/ip
```

## 日本語環境セットアップ（推奨）
文字化け防止と日本語表示のため：

```bash
# Kaliコンテナ内で実行
distrobox enter kali

# 日本語ロケール生成
sudo sed -i 's/# ja_JP.UTF-8 UTF-8/ja_JP.UTF-8 UTF-8/' /etc/locale.gen
sudo locale-gen
sudo update-locale LANG=ja_JP.UTF-8

# 日本語フォントインストール
sudo apt update
sudo apt install -y fonts-noto-cjk fonts-noto-color-emoji

# 日本語入力環境設定（<ffffffff>文字化け対策）
echo 'export GTK_IM_MODULE=xim' >> ~/.zshrc
echo 'export QT_IM_MODULE=xim' >> ~/.zshrc
echo 'export XMODIFIERS=@im=fcitx' >> ~/.zshrc
source ~/.zshrc
exit

# コンテナ再起動で設定適用
distrobox enter kali
```

## 権限修正（必要に応じて）
distrobox作成後、一部のアプリケーション（Wiresharkなど）で権限エラーが発生する場合：

```bash
# ホストシステムで実行
sudo chown -R $USER:$USER $HOME/distrobox/kali/.config
sudo chown -R $USER:$USER $HOME/distrobox/kali/.java
```
