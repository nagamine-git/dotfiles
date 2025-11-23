#!/usr/bin/env bash

# DroidCam v4l2loopback setup with automatic device detection
# Sets up v4l2loopback and finds the latest device

set -eu

echo "Setting up v4l2loopback for DroidCam..."

# Remove existing v4l2loopback module if loaded
if lsmod | grep -q v4l2loopback; then
    echo "Removing existing v4l2loopback module..."
    sudo modprobe -r v4l2loopback || true
    sleep 1
fi

# Load v4l2loopback with DroidCam settings
echo "Loading v4l2loopback module..."
sudo modprobe v4l2loopback devices=1 exclusive_caps=1 card_label="DroidCam 1920" max_width=1920 max_height=1080

# Wait for device to be created
sleep 2

# Find the latest loopback device
latest_device=""
max_num=0

# Check v4l2-ctl output for loopback devices
if command -v v4l2-ctl >/dev/null 2>&1; then
    v4l2_output=$(v4l2-ctl --list-devices 2>/dev/null || true)
    
    if echo "$v4l2_output" | grep -q "platform:v4l2loopback"; then
        # Extract device paths from v4l2-ctl output
        loopback_devices=$(echo "$v4l2_output" | grep -A1 "platform:v4l2loopback" | grep "/dev/video" || true)
        
        for device in $loopback_devices; do
            if [ -e "$device" ]; then
                device_num=$(echo "$device" | sed 's|/dev/video||')
                if [ "$device_num" -gt "$max_num" ]; then
                    max_num=$device_num
                    latest_device="$device"
                fi
            fi
        done
    fi
fi

# Fallback: check all video devices and find the highest numbered one
if [ -z "$latest_device" ]; then
    for device in /dev/video*; do
        if [ -e "$device" ] && [ -c "$device" ] && [ -r "$device" ]; then
            device_num=$(echo "$device" | sed 's|/dev/video||')
            if [ "$device_num" -gt "$max_num" ]; then
                max_num=$device_num
                latest_device="$device"
            fi
        fi
    done
fi

# Report results and create symlink
if [ -n "$latest_device" ] && [ -c "$latest_device" ]; then
    echo "Latest loopback device found: $latest_device"
    ln -sf "$latest_device" "/tmp/droidcam_device" 2>/dev/null || true
    echo "DroidCam device ready: $latest_device"
else
    echo "No loopback device found"
    exit 1
fi
