echo 'Restarting keyboard setup...'
set -eu
fcitx5 -r -d
sleep 1
systemctl --user restart fusuma
sleep 1
$HOME/.local/bin/apply-custom-xkb.sh
echo 'Keyboard setup restarted.'