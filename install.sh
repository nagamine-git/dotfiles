#!/usr/bin/env bash
set -euo pipefail

BINARY_NAME="wolow-companion"
INSTALL_DIR="/usr/local/bin"
SERVICE_DIR="/etc/systemd/system"
SERVICE_NAME="wolow-companion.service"
POLKIT_DIR="/etc/polkit-1/rules.d"
POLKIT_RULES="50-wolow-companion.rules"

echo "Installing Wolow Companion..."

# Install binary
sudo install -Dm755 "$BINARY_NAME" "$INSTALL_DIR/$BINARY_NAME"

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
