# CaptiX Implementation Log

Tracks implementation progress through all development phases.

---

## Phase 1: Project Structure & Basic X11 Screen Capture ✅

**Date:** September 29, 2025
**Commits:** `767bc6e`, `600e27b`

**Completed:**
- Project structure with `utils/` package
- Full screen and area-based capture via python-xlib
- PNG saving with timestamp naming
- CLI interface: `--screenshot`, `--area`, `--info`, `--no-cursor`, `--output`
- Multi-monitor support via RandR extension

---

## Phase 2: Clipboard Integration ✅

**Date:** September 29, 2025

**Completed:**
- File-based clipboard using xclip
- `--no-clipboard` and `--test-clipboard` CLI options
- Automatic clipboard copy for all captures

---

## Phase 2.1: Native Cursor Capture Enhancement ✅

**Date:** September 29, 2025

**Completed:**
- XFixes extension integration via ctypes
- True cursor appearance with themes and animations
- ARGB to RGBA conversion with hotspot positioning
- Eliminated manual cursor drawing

---

## Phase 3: Window Detection & Pure Window Capture ✅

**Date:** September 29, 2025
**Commit:** `4a9ac49`

**Completed:**
- Window detection at coordinates using python-xlib
- Window geometry with decoration handling
- XComposite integration for pure window content capture (no overlaps)
- CLI: `--window-at`, `--window-pure-at`, `--list-windows`, `--window-info`
- Fixed negative coordinate issue via hierarchy walking

---

## Phase 4: Screenshot UI with Area Selection ✅

**Date:** September 29 - October 3, 2025

**Completed Blocks:**

### 4.1-4.3: PyQt6 Overlay Framework
- Full-screen transparent overlay with frozen background
- 0.25s fade-in animation (0% to 50% opacity)

### 4.4: Window Detection & Highlighting
- Real-time window highlighting with content preview
- X11 stack walking with overlay exclusion

### 4.5: Mouse Event System
- Click classification: single click (≤200ms, <5px) vs drag
- Window/desktop/area capture routing

### 4.6: Temporal Consistency Capture
- Pre-capture all windows at overlay startup
- Enhanced file naming: `sc_YYYY-MM-DD_HHMMSS_<suffix>.png`
- WYSIWYG - all captures from same frozen moment

### 4.7: Selection Rectangle Drawing
- Click-and-drag with 2px cyan border
- Dark overlay excluded from selection area

### 4.8-4.9: Magnifier Widget
- 210x210px window with 10x zoom
- 21x21 pixel grid with center pixel highlight
- Real-time coordinates and crosshair guidelines

### 4.10: Selection Dimensions Display
- "W × H" format anchored bottom-right inside selection
- Bottom-left magnifier positioning to avoid overlap

### 4.11: Optimization & Polish
- Workspace filtering (71% window reduction: 14 → 4 windows)
- Minimized window detection and exclusion
- Concurrent fade-in animation start
- Crosshair guidelines for precision targeting
- Right-click window preview toggle

### 4.12: Frame Extents Detection & Border-Free Capture
- `_GTK_FRAME_EXTENTS` detection for GTK apps with invisible borders
- Content-only window capture excluding borders at capture time
- Border-aware cursor positioning
- Highlighting geometry matches captured content
- Eliminated post-processing need

---

## Phase 5: Global Hotkey System ✅

**Date:** October 31, 2025
**Commit:** `c1313fb`

**Completed:**
- GNOME keyboard shortcut via gsettings (Ctrl+Shift+X)
- Installation script with dependency checking
- Wrapper script in `~/.local/bin/captix`
- Uninstallation script with cleanup
- **No daemon required** - GNOME handles hotkey listening

**Architecture Decision:**
- Native GNOME shortcuts instead of daemon for screenshots
- Zero resource overhead when not capturing
- Daemon only needed for video recording state (Phase 7)

---

## Phase 6: FFmpeg Integration & Video Recording - PLANNED

**Goals:**
- FFmpeg wrapper for screen recording
- Audio capture (PulseAudio/PipeWire)
- Reuse screenshot UI for area selection

---

## Phase 7: Recording Control Panel & Daemon - PLANNED

**Goals:**
- Floating control panel with timer and file size
- Background daemon for recording state management
- Stop/Abort buttons and area indicators

---

## Phase 8: Notifications & Polish ✅

**Date:** November 1, 2025

**Completed:**
- Desktop notifications with file size and path display
- Clickable "Open Folder" action using GObject Notify
- Sound feedback with system themes (camera-shutter.oga)
- Integrated into all screenshot capture modes
- Subprocess-based notification for reliable action handling
- Fallback to simple notify-send when needed

---

## Phase 9: Documentation & Distribution - PLANNED

**Goals:**
- Complete documentation
- PyInstaller packaging
- System integration
