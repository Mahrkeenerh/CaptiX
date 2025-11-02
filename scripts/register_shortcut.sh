#!/bin/bash
#
# Register CaptiX GNOME keyboard shortcut
#

BIN_DIR="$HOME/.local/bin"
name="CaptiX Screenshot"
command="$BIN_DIR/captix --ui"
binding="<Ctrl><Shift>x"

# Get current custom keybindings list
current_bindings=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)

# Check if CaptiX shortcut already exists
existing_slot=""
for slot_path in $(echo "$current_bindings" | grep -o "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom[0-9]*/" | sort -u); do
    existing_name=$(gsettings get org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$slot_path name 2>/dev/null)
    if [ "$existing_name" = "'CaptiX Screenshot'" ]; then
        existing_slot="$slot_path"
        break
    fi
done

# If found, update existing slot; otherwise find next available
if [ -n "$existing_slot" ]; then
    slot_path="$existing_slot"
    echo "✓ Found existing CaptiX shortcut, updating..."
else
    # Find next available custom keybinding slot
    slot_num=0
    while true; do
        slot_path="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom${slot_num}/"
        if echo "$current_bindings" | grep -q "$slot_path"; then
            ((slot_num++))
        else
            break
        fi
    done
fi

# Only add to bindings list if it's a new slot
if [ -z "$existing_slot" ]; then
    # Add our new slot to the list using Python
    new_bindings=$(python3 << EOF
import sys
current = """$current_bindings"""
slot = """$slot_path"""

# Parse the current bindings (it's a GVariant array string)
if current in ["@as []", "[]"]:
    print(f"['{slot}']")
else:
    # Remove brackets and split by comma
    items = current.strip("[]").split(",")
    items = [item.strip().strip("'\"") for item in items if item.strip()]
    items.append(slot)
    # Format back
    formatted = ", ".join(f"'{item}'" for item in items)
    print(f"[{formatted}]")
EOF
)

    # Set the new bindings list
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$new_bindings"
fi

# Set our keybinding properties
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$slot_path name "$name"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$slot_path command "$command"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$slot_path binding "$binding"

echo "✓ Keyboard shortcut registered: Ctrl+Shift+X → captix --ui"
echo "  This allows the shortcut to work even without the daemon running"
