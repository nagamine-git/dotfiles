#!/usr/bin/env bash
# am5-itx: EPP balance_power を有効化 (上限は変えない)。sudo で実行。
set -eu
cd "$(dirname "$0")"
install -D -m 644 cpu-epp.conf /etc/tmpfiles.d/cpu-epp.conf
systemctl disable --now power-profiles-daemon.service || true
systemctl mask power-profiles-daemon.service
systemd-tmpfiles --create /etc/tmpfiles.d/cpu-epp.conf
sort -u /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference
