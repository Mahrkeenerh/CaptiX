# CaptiX - Agent Context

## Overview

CaptiX is a screenshot and screen recording tool for Linux X11. It provides an interactive overlay interface for capturing screens, windows, or custom areas with pixel-perfect precision.

## Quick Commands

```bash
# Launch screenshot mode (interactive overlay)
captix --ui

# Launch video recording mode
captix --video

# Take full screen screenshot (non-interactive)
captix --screenshot

# Take screenshot of specific area
captix --screenshot --area 100,100,800,600

# Capture window at specific coordinates
captix --screenshot --window-at 500,300

# List visible windows
captix --list-windows

# Display system info
captix --info
```

## Keyboard Shortcuts (GNOME)

| Shortcut | Action |
|----------|--------|
| Ctrl+Shift+X | Launch screenshot mode |
| Super+Shift+X | Launch video recording mode |

## Configuration

- Config directory: `~/.config/captix/`
- Screenshots saved to: `~/Pictures/Screenshots/` (organized in monthly subfolders)
- Recordings saved to: `~/Videos/Recordings/` (organized in monthly subfolders)

## File Locations

- Launcher symlink: `~/.local/bin/captix`
- Desktop entry: `~/.local/share/applications/captix.desktop`
- Repository: Runs directly from git clone location

## Architecture

Key modules in `captix/`:
- `cli.py` - Command-line interface and argument parsing
- `ui.py` - PyQt6 GUI overlay implementation
- `utils/capture.py` - Screenshot capture logic
- `utils/video_recorder.py` - Video recording with FFmpeg
- `utils/window_detect.py` - X11 window detection
- `utils/notifications.py` - Desktop notifications
- `utils/recording_panel.py` - Recording control UI

## Troubleshooting

### Overlay does not appear

1. Check if running X11 (not Wayland):
   ```bash
   echo $XDG_SESSION_TYPE  # Must output "x11"
   ```
2. If on Wayland, switch to X11 session at login screen

### Clipboard not working

Install xclip:
```bash
sudo apt install xclip
```

### Hotkeys not working

1. Check GNOME Settings -> Keyboard -> Custom Shortcuts
2. Look for "CaptiX Screenshot" and "CaptiX Video Recording" entries
3. Re-run `./install.sh` to re-register shortcuts

### Overlay freezes or becomes unresponsive

1. Press Escape to cancel
2. If stuck: Press Super key to open Activities view and close CaptiX window
3. Last resort: `pkill -f captix` or `pkill -f "python.*captix"`

### Video recording has no audio

Ensure PulseAudio or PipeWire is running:
```bash
pactl info
```

### Cannot find captix command

Ensure `~/.local/bin` is in PATH:
```bash
echo $PATH | grep -q "$HOME/.local/bin" && echo "OK" || echo "Not in PATH"
```

Add to PATH by editing `~/.bashrc` or `~/.zshrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Missing dependencies

Install required system packages:
```bash
sudo apt install python3-xlib python3-pyqt6 xclip ffmpeg
```

## System Requirements

- Linux with X11 (Wayland not supported)
- Python 3.10+
- PyQt6
- python3-xlib
- xclip (for clipboard)
- ffmpeg (for video recording)
- GNOME desktop (for hotkey registration)

## Reinstall/Update

```bash
cd /path/to/CaptiX
./install.sh  # Idempotent - safe to run multiple times
```

## Uninstall

```bash
./uninstall.sh
```

Note: Configuration and screenshots/recordings directories are preserved after uninstall.
