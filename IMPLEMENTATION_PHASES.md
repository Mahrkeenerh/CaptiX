# CaptiX Implementation Phases

## Overview
This document outlines the development phases for CaptiX, a fast screenshot and screen recording tool for Linux X11. The phases are structured to deliver working functionality incrementally, focusing on core features first.

---

## Phase 1: Project Structure & Basic X11 Screen Capture

### Goals
- Set up basic project structure
- Implement core X11 screen capture functionality
- Get basic screenshot saving working

### Tasks
1. **Project Setup**
   - Create directory structure according to specification
   - Initialize git repository
   - Install python-xlib and Pillow as needed

2. **Core Screen Capture** (`utils/capture.py`)
   - Full screen capture with python-xlib
   - Area-based capture (x, y, width, height)
   - Native cursor capture using XFixes extension (✅ Enhanced beyond original plan)
   - Multi-monitor support
   - Save screenshots to PNG files

3. **Basic File Operations**
   - File naming with timestamps
   - Directory creation (~/Pictures/Screenshots)
   - Basic error handling

4. **Simple CLI Interface** (`main.py`)
   - Command-line argument parsing
   - Basic screenshot command (--screenshot)
   - Direct capture without UI

### Deliverables
- Working screen capture system
- Screenshots saving to files
- Basic command-line interface

---

## Phase 2: Clipboard Integration

### Goals
- Add clipboard functionality to screenshots
- Ensure cross-desktop compatibility

### Tasks
1. **Clipboard Integration** (`utils/clipboard.py`)
   - Image to clipboard using Pillow
   - X11 clipboard handling
   - Error handling for clipboard failures

2. **Integration with Capture System**
   - Modify capture.py to support clipboard copying
   - Always copy screenshots to clipboard
   - Handle both file saving and clipboard simultaneously

### Deliverables
- Screenshots automatically copied to clipboard
- Cross-desktop clipboard compatibility

---

## Phase 3: Window Detection

### Goals
- Implement window detection and geometry calculation
- Support clicking on windows for targeted capture

### Tasks
1. **Window Detection** (`utils/window_detect.py`)
   - Window-at-position detection using python-xlib
   - Window geometry calculation (with decorations)
   - Root window (desktop) detection
   - Handle different window managers

2. **Enhanced Capture Modes**
   - Extend CLI to support window capture
   - Full screen vs window vs custom area modes
   - Window frame handling (with decorations)

### Deliverables
- Reliable window detection system
- Window-specific capture functionality

---

## Phase 4: Screenshot UI with Area Selection

### Goals
- Create full-screen overlay interface for area selection
- Implement selection rectangle drawing
- Add pixel-perfect magnifier
- Complete interactive screenshot workflow

### Tasks
1. **Screenshot Overlay** (`screenshot_ui.py`)
   - PyQt6 full-screen transparent window
   - Install PyQt6 as needed
   - Frozen screen background with cursor
   - Dark overlay (70% opacity)
   - Mouse event handling (click, drag, release)

2. **Selection Interface**
   - Rectangle selection drawing
   - Clear area within selection
   - Bright selection border (2px)
   - Real-time dimension display

3. **Magnifier Widget** (`utils/magnifier.py`)
   - 150x150px zoom window
   - 15-20x magnification
   - Pixel grid overlay
   - Cursor position display (X, Y coordinates)
   - Selection dimensions during drag

4. **Interaction Logic**
   - Single click detection (window/desktop)
   - Drag selection handling
   - Escape key cancellation
   - Immediate capture on mouse release

### Deliverables
- Complete interactive screenshot functionality
- Working magnifier
- Pixel-perfect selection
- Full user experience as specified

---

## Phase 5: Global Hotkey System & Daemon

### Goals
- Implement global hotkey listening
- Create background daemon
- Connect hotkeys to screenshot functionality

### Tasks
1. **Hotkey Daemon** (`daemon.py`)
   - Install pynput as needed
   - pynput global hotkey registration
   - Process spawning for screenshot UI
   - Basic configuration for hotkeys

2. **Configuration System** (`config.py`)
   - JSON config file loading/saving
   - Default configuration creation
   - Hotkey parsing and validation
   - Directory path expansion (`~/` handling)

3. **Process Management**
   - Clean subprocess launching for screenshot UI
   - Process cleanup on exit
   - Signal handling (SIGTERM, SIGINT)

### Deliverables
- Background daemon with hotkey support
- Screenshot mode fully functional via hotkeys
- Basic configuration system

---

## Phase 6: FFmpeg Integration & Video Recording

### Goals
- Implement FFmpeg wrapper for video recording
- Create video recording with audio
- Use same selection UI for video areas

### Tasks
1. **FFmpeg Wrapper** (`utils/ffmpeg_wrapper.py`)
   - FFmpeg subprocess management
   - X11grab with cursor capture
   - PulseAudio/PipeWire audio capture
   - Basic recording start/stop functionality

2. **Audio System Detection**
   - System audio source detection
   - Microphone availability detection (optional)
   - Audio mixing configuration or system-only fallback

3. **Video Recording Logic** (`video_recorder.py`)
   - Reuse selection UI from screenshots
   - Recording parameter calculation
   - FFmpeg command generation
   - Basic file saving to ~/Videos/Recordings

4. **Integration with Daemon**
   - Add video recording hotkey to daemon
   - Process management for video recording
   - Recording state tracking

### Deliverables
- Working video recording system
- Audio capture functionality
- Integration with hotkey system

---

## Phase 7: Recording Control Panel & Area Indicators

### Goals
- Create floating recording control panel
- Implement recording area indicators
- Add recording timer and file size monitoring
- Complete video recording workflow

### Tasks
1. **Recording Control Panel** (`recording_panel.py`)
   - Always-on-top floating window using PyQt6
   - Recording timer (HH:MM:SS)
   - Real-time file size estimation
   - Stop/Abort buttons

2. **Recording Area Indicators**
   - Static red border overlay (non-fullscreen recordings)
   - Semi-transparent border rendering
   - Proper positioning and sizing

3. **File Size Monitoring**
   - Real-time file size checking
   - Estimated size calculation
   - Timer updates every second

4. **Recording Controls**
   - Stop recording functionality
   - Abort recording with file cleanup
   - Second hotkey press to stop recording

### Deliverables
- Complete video recording functionality
- Professional control panel interface
- Visual recording indicators
- Full recording workflow

---

## Phase 8: Notifications & Polish

### Goals
- Add desktop notifications
- Polish the user experience
- Final testing and bug fixes

### Tasks
1. **Desktop Notifications** (`utils/notifications.py`)
   - Install notify2 or use DBus directly
   - Desktop notifications (notify-send/DBus)
   - Screenshot saved notifications with file size
   - Recording completion notifications with duration/size

2. **Notification Integration**
   - Add notifications to screenshot workflow
   - Add notifications to video recording workflow
   - Error notifications for failures
   - Actual file size reporting

3. **UI Polish & Bug Fixes**
   - Smooth overlay transitions
   - Better error messages
   - Handle edge cases
   - Final testing across different setups

### Deliverables
- Complete notification system
- Polished user experience
- Stable application ready for use

---

## Phase 9: Documentation & Distribution

### Goals
- Create comprehensive documentation
- Set up distribution system
- Package for easy installation

### Tasks
1. **Requirements & Dependencies**
   - Create final requirements.txt from installed packages
   - Document system requirements (FFmpeg, etc.)
   - Version pinning for stability

2. **Distribution Setup**
   - Create setup.py for PyInstaller
   - Single executable creation
   - Asset bundling

3. **System Integration Files**
   - Systemd user service file
   - Desktop entry file
   - Icon assets
   - Installation/uninstallation scripts

4. **Documentation**
   - User guide
   - Installation instructions
   - Configuration reference
   - Troubleshooting guide

### Deliverables
- Distributable application package
- Complete documentation
- Installation system
- Release-ready package

---

## Development Guidelines

### Code Quality Standards
- Python 3.10+ compatibility
- Type hints for all functions
- Comprehensive error handling

### Git Workflow
- Feature branches for each phase
- Regular commits with clear messages
- Tag releases for each phase completion

### Dependencies Management
- Install libraries as needed during development
- Create requirements.txt at the end by freezing working environment
- Minimal dependency footprint