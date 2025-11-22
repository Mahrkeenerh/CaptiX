#!/bin/bash
#
# Register CaptiX GNOME keyboard shortcuts (Screenshot + Video Recording)
#

BIN_DIR="$HOME/.local/bin"

# Define shortcuts: name, command, binding
declare -A shortcuts
shortcuts["CaptiX Screenshot"]="$BIN_DIR/captix --ui|<Ctrl><Shift>x"
shortcuts["CaptiX Video Recording"]="$BIN_DIR/captix --video|<Super><Shift>x"

# Get current custom keybindings list
current_bindings=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)

# Find next available slot number
get_next_slot() {
    local slot_num=0
    while true; do
        local slot_path="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom${slot_num}/"
        if echo "$current_bindings" | grep -q "$slot_path"; then
            ((slot_num++))
        else
            echo "$slot_path"
            return
        fi
    done
}

# Track slots that need to be added to bindings list
new_slots=()

# Process each shortcut
for name in "${!shortcuts[@]}"; do
    IFS='|' read -r command binding <<< "${shortcuts[$name]}"

    # Check if this shortcut already exists
    existing_slot=""
    for slot_path in $(echo "$current_bindings" | grep -o "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom[0-9]*/" | sort -u); do
        existing_name=$(gsettings get org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$slot_path name 2>/dev/null)
        if [ "$existing_name" = "'$name'" ]; then
            existing_slot="$slot_path"
            break
        fi
    done

    # Use existing slot or find new one
    if [ -n "$existing_slot" ]; then
        slot_path="$existing_slot"
        echo "✓ Found existing '$name' shortcut, updating..."
    else
        slot_path=$(get_next_slot)
        new_slots+=("$slot_path")
        echo "✓ Registering new '$name' shortcut..."
        # Update current_bindings for next iteration
        if [ "$current_bindings" = "@as []" ] || [ "$current_bindings" = "[]" ]; then
            current_bindings="['$slot_path']"
        else
            current_bindings=$(echo "$current_bindings" | sed "s/]$/, '$slot_path']/")
        fi
    fi

    # Set keybinding properties
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$slot_path name "$name"
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$slot_path command "$command"
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$slot_path binding "$binding"
done

# Update the bindings list if we added new slots
if [ ${#new_slots[@]} -gt 0 ]; then
    # Rebuild bindings list with all slots (existing + new)
    final_bindings=$(python3 << EOF
import sys
current = """$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)"""
new_slots = """${new_slots[@]}""".split()

# Parse current bindings
if current in ["@as []", "[]"]:
    items = []
else:
    items = current.strip("[]").split(",")
    items = [item.strip().strip("'\"") for item in items if item.strip()]

# Add new slots
for slot in new_slots:
    if slot not in items:
        items.append(slot)

# Format as GVariant array
formatted = ", ".join(f"'{item}'" for item in items)
print(f"[{formatted}]")
EOF
)
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$final_bindings"
fi

echo ""
echo "✓ Keyboard shortcuts registered:"
echo "  Ctrl+Shift+X → Screenshot (captix --ui)"
echo "  Super+Shift+X → Video Recording (captix --video)"
echo "  Shortcuts work even without the daemon running"
