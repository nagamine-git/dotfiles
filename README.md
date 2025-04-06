# Mozc リビルド手順: HIRAGANAをデフォルトにする

以下のコマンドを順番に実行します：

```bash
# 一時作業用ディレクトリを作成
mkdir -p /tmp/mozc-build
cd /tmp/mozc-build

# 必要なパッケージをインストール
sudo apt install build-essential devscripts -y
sudo apt build-dep ibus-mozc -y
apt source ibus-mozc

# Mozcディレクトリを特定（複数ファイルが含まれるため -d ではなく明示的に探す）
MOZC_DIR=$(find . -type d -name "mozc-*" | head -1)
echo "ビルドディレクトリ: $MOZC_DIR"

# CompositionModeの順序を変更（HIRAGANAをデフォルトにする）
sed -i 's/DIRECT = 0;/DIRECT = 1;/g' $MOZC_DIR/src/protocol/commands.proto
sed -i 's/HIRAGANA = 1;/HIRAGANA = 0;/g' $MOZC_DIR/src/protocol/commands.proto

# ビルド
cd $MOZC_DIR
dpkg-buildpackage -us -uc -b

# インストール
cd /tmp/mozc-build
sudo dpkg -i ibus-mozc_*.deb

# 完了
echo "インストール完了。システムを再起動してください。"
```

注意: /tmp ディレクトリは再起動時に消去されるため、再ビルドが必要な場合は最初からやり直す必要があります。
