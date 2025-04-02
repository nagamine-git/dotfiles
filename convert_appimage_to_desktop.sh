#!/bin/bash

# Validate input
if [ -z "$1" ]; then
    echo "Error: No AppImage provided. Usage: $0 <AppImage> [Icon]"
    exit 1
fi

APPIMAGE=$1
if [[ ! "$APPIMAGE" =~ \.AppImage$ ]]; then
    echo "Error: The file must have a .AppImage extension."
    exit 1
fi

ICON=${2:-}
APPNAME=$(basename "$APPIMAGE" .AppImage)
APPIMAGE_DEST="/opt/$APPNAME.AppImage"
ICON_DEST="/opt/$(basename "$ICON")"

# Determine the correct home directory
if [ -n "$SUDO_USER" ]; then
    USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
else
    USER_HOME=$HOME
fi

DESKTOP_PATH="$USER_HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_PATH/$APPNAME.desktop"

# Function to show a loader animation
show_loader() {
    echo -ne "$1"
    for i in {1..3}; do
        echo -ne "."
        sleep 0.5
    done
    echo -e " \033[32mDone!\033[0m"
}

# Make AppImage executable
chmod +x "$APPIMAGE"
show_loader "Making AppImage executable"

# Move AppImage to /opt
sudo mv "$APPIMAGE" "$APPIMAGE_DEST"
show_loader "Moving AppImage to /opt"

# Move icon to /opt if provided
if [ -n "$ICON" ]; then
    if [ ! -f "$ICON" ]; then
        echo "Error: Icon file $ICON does not exist."
        exit 1
    fi
    sudo mv "$ICON" "$ICON_DEST"
    show_loader "Moving icon to /opt"
fi

# Navigate to the target directory
cd "$DESKTOP_PATH" || exit

# Create the .desktop file
touch "$APPNAME.desktop"
cat > "$APPNAME.desktop" <<EOF
[Desktop Entry]
Name=$APPNAME
Comment=Application launcher for $APPNAME
Exec=$APPIMAGE_DEST
Terminal=false
Type=Application
Categories=Utility
$( [ -n "$ICON" ] && echo "Icon=$ICON_DEST" || echo "" )
EOF
show_loader "Creating .desktop file"

# Update desktop database
update-desktop-database "$DESKTOP_PATH" &>/dev/null
show_loader "Updating desktop database"

# Final message
cat <<EOF

All set! Your application has been successfully added to the menu.
Details: 
  AppImage: $APPIMAGE_DEST
  Icon: ${ICON:+$ICON_DEST (or not set)}
  Desktop File: $DESKTOP_FILE

You can now find "$APPNAME" in your application menu! 🎉
EOF
