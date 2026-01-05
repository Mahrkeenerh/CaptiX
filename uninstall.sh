#!/bin/bash
#
# CaptiX Uninstallation Script
# Removes CaptiX daemon, scripts, and configuration
#

set -e

BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/captix"
AUTOSTART_DIR="$HOME/.config/autostart"

echo "===================================="
echo "CaptiX Uninstallation"
echo "===================================="
echo ""

# Remove launcher scripts
echo ""
echo "Removing launcher scripts..."
rm -f "$BIN_DIR/captix"
echo "✓ Launcher scripts removed"

# Remove desktop entry symlink
echo ""
echo "Removing desktop entry..."
rm -f ~/.local/share/applications/captix.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true
echo "✓ Desktop entry removed"

# Remove GNOME keyboard shortcut
echo ""
echo "Removing GNOME keyboard shortcut..."

unregister_gnome_shortcut() {
    # Get current custom keybindings list
    current_bindings=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)

    # Find and remove CaptiX shortcut
    for slot_num in {0..20}; do
        slot_path="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom${slot_num}/"

        # Check if this slot exists
        if echo "$current_bindings" | grep -q "$slot_path"; then
            # Check if it's our shortcut
            name=$(gsettings get org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$slot_path name 2>/dev/null || echo "")
            if echo "$name" | grep -q "CaptiX"; then
                # Remove from list using Python
                new_bindings=$(python3 << EOF
current = """$current_bindings"""
slot = """$slot_path"""

# Parse the current bindings
if current not in ["@as []", "[]"]:
    items = current.strip("[]").split(",")
    items = [item.strip().strip("'\"") for item in items if item.strip()]
    # Remove our slot
    items = [item for item in items if slot not in item]
    if items:
        formatted = ", ".join(f"'{item}'" for item in items)
        print(f"[{formatted}]")
    else:
        print("@as []")
else:
    print("@as []")
EOF
)
                # Update the bindings list
                gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$new_bindings"

                # Reset the slot
                gsettings reset org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$slot_path name 2>/dev/null || true
                gsettings reset org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$slot_path command 2>/dev/null || true
                gsettings reset org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$slot_path binding 2>/dev/null || true

                echo "✓ Keyboard shortcut removed"
                return
            fi
        fi
    done

    echo "→ No CaptiX keyboard shortcut found"
}

# Only unregister if gsettings is available
if command -v gsettings &> /dev/null; then
    unregister_gnome_shortcut
else
    echo "→ gsettings not found, skipping"
fi

echo ""
echo "===================================="
echo "Uninstallation Complete!"
echo "===================================="
echo ""
echo "CaptiX has been removed from your system."
echo ""
echo "Note: The following were preserved:"
echo "  - Configuration: $CONFIG_DIR"
echo "  - Screenshots: ~/Gallery/Screenshots"
echo "  - Recordings: ~/Gallery/Recordings"
echo "  - Project directory and virtual environment"
echo ""
