#!/bin/bash
#
# CaptiX Installation Script
# Installs CaptiX with hotkey daemon and autostart support
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/captix"
AUTOSTART_DIR="$HOME/.config/autostart"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "===================================="
echo "CaptiX Installation"
echo "===================================="
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is required but not installed"
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"

# Check for required system packages
echo ""
echo "Checking system dependencies..."

missing_deps=()

if ! python3 -c "import Xlib" 2>/dev/null; then
    missing_deps+=("python3-xlib")
fi

if ! python3 -c "from PyQt6 import QtWidgets" 2>/dev/null; then
    missing_deps+=("python3-pyqt6")
fi

if ! command -v xclip &> /dev/null; then
    missing_deps+=("xclip")
fi

if [ ${#missing_deps[@]} -gt 0 ]; then
    echo ""
    echo "⚠️  Missing system dependencies:"
    for dep in "${missing_deps[@]}"; do
        echo "   - $dep"
    done
    echo ""
    echo "Install with:"
    echo "  sudo apt install ${missing_deps[*]}"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✓ All system dependencies found"
fi

# Create virtual environment
echo ""
echo "Setting up virtual environment..."

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate and install Python dependencies
source "$VENV_DIR/bin/activate"

echo ""
echo "Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt 2>/dev/null || echo "⚠ requirements.txt not found, skipping pip install"

echo "✓ Python dependencies setup complete"

# Create directories
echo ""
echo "Creating directories..."
mkdir -p "$BIN_DIR"
mkdir -p "$AUTOSTART_DIR"
mkdir -p "$HOME/Pictures/Screenshots"
mkdir -p "$HOME/Videos/Recordings"

echo "✓ Directories created"

# Create wrapper scripts
echo ""
echo "Creating launcher scripts..."

# Main captix launcher
cat > "$BIN_DIR/captix" << EOF
#!/bin/bash
source "$VENV_DIR/bin/activate"
cd "$SCRIPT_DIR"
exec python3 -m captix "\$@"
EOF
chmod +x "$BIN_DIR/captix"

echo "✓ Launcher scripts created"


# Register GNOME keyboard shortcut
echo ""
echo "Registering keyboard shortcut (Ctrl+Shift+X)..."

# Only register if gsettings is available (GNOME/Pop!_OS)
if command -v gsettings &> /dev/null; then
    bash "$SCRIPT_DIR/scripts/register_shortcut.sh"
else
    echo "⚠ gsettings not found - keyboard shortcut not registered"
    echo "  Or manually add a shortcut in System Settings → Keyboard"
    echo "  Command: $BIN_DIR/captix --ui"
    echo "  Shortcut: Ctrl+Shift+X"
fi

# Check if ~/.local/bin is in PATH
echo ""
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "⚠️  ~/.local/bin is not in your PATH"
    echo ""
    echo "Add this line to your ~/.bashrc or ~/.zshrc:"
    echo '  export PATH="$HOME/.local/bin:$PATH"'
    echo ""
    echo "Then run: source ~/.bashrc (or source ~/.zshrc)"
else
    echo "✓ ~/.local/bin is in PATH"
fi

# Installation complete
echo ""
echo "===================================="
echo "Installation Complete!"
echo "===================================="
echo ""
echo "Quick Start:"
echo "  Press Ctrl+Shift+X       # Take screenshot (from anywhere)"
echo "  Press Super+Shift+X      # Record video (from anywhere)"
echo "  captix --ui              # Launch screenshot UI manually"
echo "  captix --video           # Launch video recording UI manually"
echo "  captix --screenshot      # Take screenshot via CLI"
echo ""
echo "Keyboard Shortcuts:"
echo "  Ctrl+Shift+X (Screenshot) and Super+Shift+X (Video) are registered in GNOME Settings → Keyboard"
echo ""
echo "The shortcuts are active immediately - try pressing Ctrl+Shift+X or Super+Shift+X!"
echo ""
