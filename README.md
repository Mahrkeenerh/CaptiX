# CaptiX

**Fast screenshot and screen recording tool for Linux X11** - Capture your screen with pixel-perfect precision using an intuitive overlay interface and global hotkeys.

## Disclaimer

This application was vibe-coded with Claude. I take no responsibility for it breaking your system. I developed it for myself, use it regularly, and applied best practices while developing it. It works for me - your mileage may vary. Use at your own risk.

## Features

- **Screenshot capture** - Click windows, desktop, or drag to select areas
- **Screen recording** - Record full screen, windows, or custom areas with audio
- **Pixel-perfect selection** - Magnifier with 15-20x zoom and pixel grid
- **Smart window detection** - Highlights windows under cursor
- **Global hotkeys** - Ctrl+Shift+X (screenshot), Super+Shift+X (video)
- **Clipboard integration** - Screenshots auto-copied to clipboard
- **Native cursor capture** - XFixes integration for true cursor appearance
- **Desktop notifications** - With sound and clickable folder opening

## Requirements

- Linux with X11 (Wayland not supported)
- Python 3.10+
- GNOME desktop (for hotkey registration)

## Installation

```bash
# Install system dependencies
sudo apt install python3 python3-pip python3-venv python3-xlib python3-pyqt6 xclip ffmpeg

# Clone and install
git clone https://github.com/yourusername/CaptiX.git
cd CaptiX
./install.sh
```

The installer sets up a virtual environment, installs dependencies, creates the `captix` launcher in `~/.local/bin/`, registers keyboard shortcuts, and adds CaptiX to your application menu.

**Hotkeys work immediately after installation.**

## Usage

### Hotkeys

| Shortcut | Action |
|----------|--------|
| Ctrl+Shift+X | Screenshot mode |
| Super+Shift+X | Video recording mode |

### Command Line

```bash
captix --ui                              # Interactive screenshot mode
captix --video                           # Interactive video recording mode
captix --screenshot                      # Full screen screenshot
captix --screenshot --area 100,100,800,600   # Specific area
captix --screenshot --window-at 500,300  # Window at coordinates
captix --list-windows                    # List visible windows
captix --info                            # Display system info
```

### Interactive Controls

When the overlay appears:
- **Click window** - Capture/record that window
- **Click desktop** - Capture/record full screen
- **Drag** - Select custom area
- **Right-click** - Toggle window preview (screenshot mode)
- **Escape** - Cancel

During video recording:
- Control panel shows timer and file size
- Stop button saves the recording
- Abort button cancels and deletes file
- Press Super+Shift+X again to stop recording

### Output

Files are organized into monthly subfolders:
```
Screenshots: ~/Gallery/Screenshots/YYYY-MM/Screenshot_YYYY-MM-DD_HH-MM-SS.png
Videos:      ~/Gallery/Recordings/YYYY-MM/rec_YYYY-MM-DD_HHMMSS_<type>.mkv
```

## Troubleshooting

**Overlay doesn't appear:**
```bash
echo $XDG_SESSION_TYPE  # Must be "x11", not "wayland"
```

**Clipboard not working:**
```bash
sudo apt install xclip
```

**Video recording has no audio:**
Ensure PulseAudio or PipeWire is running.

**Hotkeys not working:**
Check GNOME Settings → Keyboard → Custom Shortcuts for CaptiX entries.

**Overlay freezes:**
- Press Escape
- If stuck: Press Super to open Activities view and close CaptiX window
- Last resort: Ctrl+Alt+F3, login, run `pkill -9 python`, then Ctrl+Alt+F1 to return

## Uninstall

```bash
./uninstall.sh
```

## License

MIT License - see [LICENSE](LICENSE) file.
