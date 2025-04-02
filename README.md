```bash
# bash --version > 5.0.0
./setup.sh
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