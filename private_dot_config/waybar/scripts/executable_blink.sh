#!/bin/bash

COUNT=5
INTERVAL=0.01

for i in $(seq 1 $COUNT); do
  hyprshade on vibrance
  PID=$!
  sleep "$INTERVAL"

  hyprshade on blue-light-filter
  PID=$!
  sleep "$INTERVAL"
done

# 最後にリセット（オプション）
hyprshade auto
