#!/usr/bin/env bash

# Setup sleep backup systemd service
# This script creates a systemd service to monitor sleep wake events

set -eu

# Create systemd service
sudo tee /etc/systemd/system/sleep-backup.service > /dev/null << 'EOF'
[Unit]
Description=Sleep Wake Backup Service
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/home/tsuyoshi/.local/bin/executable_sleep_backup.sh
User=tsuyoshi
Group=tsuyoshi

[Install]
WantedBy=multi-user.target
EOF

# Create systemd timer
sudo tee /etc/systemd/system/sleep-backup.timer > /dev/null << 'EOF'
[Unit]
Description=Sleep Wake Backup Timer
Requires=sleep-backup.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=10min
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Enable and start the timer
sudo systemctl daemon-reload
sudo systemctl enable sleep-backup.timer
sudo systemctl start sleep-backup.timer

echo "Sleep backup service installed and started"
echo "Check status with: systemctl status sleep-backup.timer"
echo "View logs with: journalctl -u sleep-backup.service"



