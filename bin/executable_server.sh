#!/bin/bash

sudo pacman -Syu --noconfirm
sudo pacman -S --noconfirm openssh freerdp wayvnc
sudo systemctl enable --now sshd
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --reload
sudo systemctl enable --now xrdp
sudo firewall-cmd --permanent --add-port=3389/tcp
sudo firewall-cmd --permanent --add-port=60000-61000/udp
sudo firewall-cmd --permanent --add-port=11434/tcp
sudo firewall-cmd --reload
sudo systemctl enable --now tailscaled
sudo tailscale up
