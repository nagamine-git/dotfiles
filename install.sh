#!/usr/bin/env bash
# Wolow Companion (iPhone Wolow アプリからの遠隔電源制御 daemon) のインストーラ。
# chezmoi のブートストラップではない。Linux では run_onchange_setup.sh から
# cwd=$HOME で自動実行され、~/wolow-companion と ~/50-wolow-companion.rules を参照する。
set -euo pipefail

BINARY_NAME="wolow-companion"
INSTALL_DIR="/usr/local/bin"
SERVICE_DIR="/etc/systemd/system"
SERVICE_NAME="wolow-companion.service"
POLKIT_DIR="/etc/polkit-1/rules.d"
POLKIT_RULES="50-wolow-companion.rules"

echo "Installing Wolow Companion..."

# Install binary
# バイナリは git 管理外 (2026-07 監査で追跡廃止)。導入済みマシンは /usr/local/bin の
# 既存コピーで継続。新規マシンは既存機から ~/wolow-companion へ scp してから apply する。
if [ -f "$BINARY_NAME" ]; then
    sudo install -Dm755 "$BINARY_NAME" "$INSTALL_DIR/$BINARY_NAME"
elif [ -x "$INSTALL_DIR/$BINARY_NAME" ]; then
    echo "wolow-companion: binary not in \$HOME — keeping existing $INSTALL_DIR/$BINARY_NAME"
else
    echo "⚠ wolow-companion: binary が見つかりません。既存機から scp で配置してください (スキップ)"
    exit 0
fi

# Install systemd system service
sudo install -Dm644 /dev/stdin "$SERVICE_DIR/$SERVICE_NAME" << 'EOF'
[Unit]
Description=Wolow Companion - Remote control daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/wolow-companion
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Install polkit rules (allows daemon to ignore inhibitors for power commands)
if [ -d "$POLKIT_DIR" ]; then
    sudo install -Dm644 "$POLKIT_RULES" "$POLKIT_DIR/$POLKIT_RULES"
fi

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

echo ""
echo "Wolow Companion installed and running."
sudo systemctl status "$SERVICE_NAME" --no-pager
