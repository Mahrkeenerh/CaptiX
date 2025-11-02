# CaptiX

**Fast screenshot and screen recording tool for Linux X11** - Capture your screen with pixel-perfect precision using an intuitive overlay interface and global hotkeys.

## ⚠️ Disclaimer

This entire application was vibe-coded with Claude. I take no responsibility for it breaking your system. I developed it for myself, I use it regularly, and I applied best practices while developing it with Claude and tested it thoroughly. It works for me - your mileage may vary. Use at your own risk.

## Features

- 📸 **Intelligent screenshot capture** - Click windows, desktop, or drag to select precise areas
- 🎯 **Pixel-perfect selection** - Built-in magnifier with 15-20x zoom and pixel grid overlay
- 🪟 **Smart window detection** - Automatically detects and highlights windows under cursor
- 🖱️ **Real-time visual feedback** - See exactly what you'll capture before clicking
- 📋 **Automatic clipboard copy** - Screenshots instantly copied to clipboard
- ⚡ **Global hotkeys** - Trigger captures from anywhere (configurable)
- 🎨 **Enhanced cursor capture** - Native XFixes integration for true cursor appearance
- 🔍 **Crosshair guidelines** - Precision targeting with dash-dot alignment guides
- 🎬 **Screen recording** - Full screen, window, or area recording (planned)

## Current Status

**Phase 8 Complete** - Fully functional screenshot tool with notifications and sound feedback

✅ Working Features:
- **Global hotkey (Ctrl+Shift+X)** - Trigger screenshots from anywhere via GNOME shortcuts
- Full screen capture via CLI or interactive overlay
- Window-specific capture with pure content extraction (no overlaps)
- Precise area selection with drag interface
- Pixel-perfect magnifier with coordinates and dimensions
- Real-time window highlighting and content preview
- Clipboard integration with xclip
- Native cursor capture using XFixes extension
- Workspace filtering and concurrent window capture
- Automatic installation with keyboard shortcut registration
- Desktop notifications with sound and clickable folder opening

🚧 Planned Features:
- Phase 6: Video recording with FFmpeg
- Phase 7: Recording control panel and daemon (for video recording state)

## System Requirements

- **Linux with X11** (Wayland not currently supported)
- **Python 3.10+**
- **PyQt6** (for interactive UI)
- **xclip** (for clipboard operations)
- **D-Bus** (for single-instance control, standard on all GNOME systems)

**Verify your system:**
```bash
echo "Display Server: $XDG_SESSION_TYPE" && python3 --version
```

## Installation

### System Packages

First, install the required system packages:

```bash
sudo apt install python3 python3-pip python3-venv python3-xlib xclip
```

### Quick Install

```bash
git clone https://github.com/yourusername/CaptiX.git
cd CaptiX
./install.sh
```

The installer will:
- ✅ Set up Python virtual environment
- ✅ Install Python dependencies (PyQt6, Pillow, python-xlib)
- ✅ Install CaptiX to `~/.local/bin/`
- ✅ Register global keyboard shortcut (Ctrl+Shift+X) via GNOME settings
- ✅ Create default screenshot/video directories

**The keyboard shortcut works immediately after installation!**

## Usage

### Global Hotkey (Recommended)

Press **Ctrl+Shift+X** from anywhere to launch the screenshot overlay.

The hotkey is automatically registered during installation and works system-wide.

### Command Line Interface

**Take a screenshot:**
```bash
captix --screenshot                           # Full screen
captix --screenshot --area 100,100,800,600   # Specific area
captix --screenshot --window-at 500,300      # Window at coordinates
captix --screenshot --no-cursor              # Without cursor
captix --screenshot --no-clipboard           # Skip clipboard copy
```

**Interactive screenshot UI:**
```bash
captix --ui
```

**Window detection:**
```bash
captix --list-windows                        # List all visible windows
captix --window-info 500,300                 # Get window info at position
```

**System information:**
```bash
captix --info                                # Display screen geometry and system info
```

### Interactive UI Controls

When the overlay appears:

1. **Single click on window** - Captures that window immediately
2. **Single click on desktop** - Captures full screen immediately
3. **Click and drag** - Creates selection rectangle, captures on release
4. **Right-click** - Toggle window content preview mode
5. **Escape** - Cancel and close overlay

**While dragging:**
- Magnifier window shows 15-20x zoomed view with pixel grid
- Real-time cursor coordinates (X, Y) displayed
- Selection dimensions (Width × Height) shown in bottom-right corner
- Crosshair guidelines for precise alignment

### File Output

Screenshots are automatically saved to:
```
~/Pictures/Screenshots/Screenshot_YYYY-MM-DD_HH-MM-SS.png
```

Videos will be saved to (when implemented):
```
~/Videos/Recordings/Recording_YYYY-MM-DD_HH-MM-SS.mp4
```

## Technical Features

### Advanced Window Capture

CaptiX implements sophisticated window capture beyond basic screenshots:

- **Pure window content extraction** - Uses XComposite extension to capture window content without overlapping elements
- **Temporal consistency** - All captures taken from the same frozen moment for WYSIWYG accuracy
- **Workspace filtering** - Automatically filters windows to current workspace
- **Concurrent capture** - Captures all visible windows in parallel at overlay launch
- **Smart border detection** - Intelligent frame extent calculation for accurate window boundaries

### Enhanced Cursor Integration

- Native XFixes extension integration via ctypes
- True cursor appearance including themes and animations
- Optional cursor inclusion in screenshots
- Cursor position tracking with pixel-perfect accuracy

### Multi-Monitor Support

- RandR extension for multi-monitor geometry detection
- Automatic screen bounds calculation
- Seamless capture across all connected displays

## Configuration

Configuration files will be stored in `~/.config/captix/`:

```
~/.config/captix/
├── config.json              # Main configuration (Phase 5)
├── daemon.pid              # Daemon process ID (Phase 5)
└── layouts/                # Future: Recording presets
```

**Current hotkeys:**
- `Ctrl+Shift+X` - Screenshot mode (active now!)

**Planned hotkeys:**
- `Super+Shift+X` - Video recording mode (Phase 6)

## Development Status

### Completed Phases

#### Phase 1: Project Structure & Basic X11 Screen Capture ✅
- Core screen capture using python-xlib
- Full screen and area-based capture
- PNG file saving with timestamp naming
- CLI interface with comprehensive options

#### Phase 2: Clipboard Integration ✅
- Automatic clipboard copying using xclip
- Cross-desktop compatibility
- Optional clipboard disable flag

#### Phase 3: Window Detection ✅
- Window-at-position detection
- Window geometry calculation with decorations
- Pure window content capture (XComposite)
- Root window (desktop) detection

#### Phase 4: Screenshot UI with Area Selection ✅
- Full-screen transparent PyQt6 overlay
- Frozen screen background with cursor
- Real-time window highlighting with content preview
- Drag selection with bright border
- Pixel-perfect magnifier (150x150px, 15-20x zoom)
- Selection dimensions display
- Crosshair precision guidelines
- Enhanced temporal consistency capture system

### Upcoming Phases

#### Phase 5: Global Hotkey System ✅
- GNOME keyboard shortcut registration via gsettings
- System-wide Ctrl+Shift+X hotkey
- Automatic registration during installation
- No daemon required for screenshot functionality

#### Phase 6: FFmpeg Integration & Video Recording
- FFmpeg wrapper for screen recording
- Audio capture (PulseAudio/PipeWire)
- Cursor capture in videos
- Same selection interface as screenshots

#### Phase 7: Recording Control Panel & Daemon
- Floating control window
- Timer and file size monitoring
- Stop/Abort buttons
- Static recording area indicator
- Background daemon for recording state management (only needed for video)

#### Phase 8: Notifications & Polish
- Desktop notifications with file sizes
- Error notifications
- UI refinements and bug fixes

#### Phase 9: Documentation & Distribution
- PyInstaller packaging
- Systemd service integration
- Complete user documentation

## Troubleshooting

### PyQt6 import errors
Make sure PyQt6 is installed in your virtual environment:
```bash
source .venv/bin/activate
pip install PyQt6
```

### Clipboard not working
Install xclip:
```bash
sudo apt install xclip
```

Test clipboard functionality:
```bash
captix --test-clipboard
```

### Window detection issues
Check that python-xlib is properly installed:
```bash
python3 -c "import Xlib; print('OK')"
```

### Screenshots are blank
Verify X11 is running (not Wayland):
```bash
echo $XDG_SESSION_TYPE
```
Should output: `x11`

### Permission errors
Ensure screenshot directory exists and is writable:
```bash
mkdir -p ~/Pictures/Screenshots
ls -ld ~/Pictures/Screenshots
```

## Known Limitations

- **X11 only** - Does not support Wayland (fundamental X11 dependency)
- **No video recording yet** - Phases 6-7 in development
- **No global hotkeys yet** - Phase 5 in development, currently CLI-only
- **No notifications yet** - Phase 8 planned
- **Single display optimization** - Multi-monitor works but not fully optimized

## Dependencies

**Python Packages:**
```
python-xlib>=0.33      # X11 screen capture and window detection
Pillow>=10.0.0         # Image processing and PNG optimization
PyQt6>=6.4.0          # Interactive UI framework
dbus-python            # D-Bus integration for single-instance control
```

**System Requirements:**
- `xclip` - Clipboard operations
- `dbus` - Session bus for single-instance management (standard on GNOME)
- X11 with XComposite, XFixes, and RandR extensions
- Python 3.10 or higher

## Architecture

**Core Components:**
- `main.py` - CLI entry point and command routing
- `screenshot_ui.py` - Interactive PyQt6 overlay interface
- `utils/capture.py` - X11 screen and window capture engine
- `utils/window_detect.py` - Window detection and geometry
- `utils/clipboard.py` - Clipboard integration via xclip
- `utils/magnifier.py` - Pixel-perfect magnifier widget
- `scripts/register_shortcut.sh` - GNOME keyboard shortcut registration

**Future Components:**
- `video_recorder.py` - FFmpeg video recording (Phase 6)
- `recording_panel.py` - Recording control UI (Phase 7)
- `daemon.py` - Background daemon for video recording state (Phase 7, optional)

## Performance

- **Fast capture** - Direct X11 access with minimal overhead
- **Efficient memory** - Captures only visible windows on current workspace
- **Concurrent processing** - Parallel window capture at overlay launch
- **Optimized rendering** - Cached QPixmap conversions for smooth UI

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Credits

Built with Python, PyQt6, python-xlib, and Pillow.

Inspired by modern screenshot tools and the need for a fast, precise Linux X11 capture solution.
