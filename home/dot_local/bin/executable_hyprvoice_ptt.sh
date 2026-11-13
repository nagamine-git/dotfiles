#!/usr/bin/env bash
set -euo pipefail

USER_NAME="tsuyoshi"
user_id="$(id -u "${USER_NAME}")"
session_env="XDG_RUNTIME_DIR=/run/user/${user_id} DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${user_id}/bus"
toggle_cmd="hyprvoice toggle"

toggle_voice() {
  /usr/bin/runuser -u "${USER_NAME}" -- /bin/sh -c "${session_env} ${toggle_cmd}"
}

cleanup_needed=0
cleanup() {
  if [[ "${cleanup_needed}" -eq 1 ]]; then
    toggle_voice || true
  fi
}
trap cleanup EXIT

toggle_voice
cleanup_needed=1

while read -r line; do
  read -r -a parts <<< "${line}"
  (( ${#parts[@]} < 2 )) && continue
  action_index=$((${#parts[@]} - 1))
  key_index=$((${#parts[@]} - 2))
  action="${parts[${action_index}]}"
  key="${parts[${key_index}]}"
  case "${key}" in
    space|leftshift|rightshift)
      if [[ "${action}" == "up" ]]; then
        break
      fi
      ;;
  esac
done < <(/usr/bin/keyd monitor)

cleanup_needed=0
toggle_voice
