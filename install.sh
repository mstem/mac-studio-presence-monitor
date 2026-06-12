#!/bin/bash
set -euo pipefail

INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/usr/local/etc/mac-studio-monitor"
LOG_DIR="/usr/local/var/log"
PLIST_DEST="/Library/LaunchDaemons/com.evens.macstudio-presence.plist"
LABEL="com.evens.macstudio-presence"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo install -d -m 755 "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR"
sudo install -m 755 "$SCRIPT_DIR/mac-studio-presence-monitor.py" "$INSTALL_DIR/mac-studio-presence-monitor.py"

if [ ! -f "$CONFIG_DIR/config.json" ]; then
    SRC_CONFIG="$SCRIPT_DIR/config.example.json"
    [ -f "$SCRIPT_DIR/config.json" ] && SRC_CONFIG="$SCRIPT_DIR/config.json"
    sudo install -m 600 "$SRC_CONFIG" "$CONFIG_DIR/config.json"
    echo "Wrote config to $CONFIG_DIR/config.json"
fi

sudo install -m 644 "$SCRIPT_DIR/com.evens.macstudio-presence.plist" "$PLIST_DEST"

sudo launchctl bootout system "$PLIST_DEST" 2>/dev/null || true
sudo launchctl bootstrap system "$PLIST_DEST"
sudo launchctl kickstart -k "system/$LABEL"

echo "Installed and started $LABEL"
echo "Logs: $LOG_DIR/mac-studio-presence-monitor.log"
