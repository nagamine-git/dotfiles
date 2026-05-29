#!/usr/bin/env bash
set -euo pipefail

BINARY_NAME="wolow-companion"
INSTALL_DIR="/usr/local/bin"
SERVICE_DIR="/etc/systemd/system"
SERVICE_NAME="wolow-companion.service"
POLKIT_DIR="/etc/polkit-1/rules.d"
POLKIT_RULES="50-wolow-companion.rules"

echo "Uninstalling Wolow Companion..."

# Stop and disable the service if it exists
if sudo systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    sudo systemctl stop "$SERVICE_NAME"
fi

if sudo systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    sudo systemctl disable "$SERVICE_NAME"
fi

# Remove service file
if [ -f "$SERVICE_DIR/$SERVICE_NAME" ]; then
    sudo rm -f "$SERVICE_DIR/$SERVICE_NAME"
    sudo systemctl daemon-reload
fi

# Remove polkit rules
if [ -f "$POLKIT_DIR/$POLKIT_RULES" ]; then
    sudo rm -f "$POLKIT_DIR/$POLKIT_RULES"
fi

# Remove binary
if [ -f "$INSTALL_DIR/$BINARY_NAME" ]; then
    sudo rm -f "$INSTALL_DIR/$BINARY_NAME"
fi

echo "Wolow Companion uninstalled."
