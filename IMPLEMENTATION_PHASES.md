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
   - *Note: Implementation also includes pure window content capture (no overlaps) using XComposite extension*

### Deliverables
- Reliable window detection system
- Window-specific capture functionality

---

## Phase 4: Screenshot UI with Area Selection

### Goals
- Create interactive overlay interface with real-time window highlighting
- Implement drag selection with magnifier
- Add pixel-perfect selection tools
- Provide visual feedback for window detection

### Implementation Blocks

#### Block 4.1: PyQt6 Setup & Basic Overlay
- Install PyQt6 dependency
- Create basic full-screen transparent window
- Test window appears and covers all monitors
- Add escape key to close window

#### Block 4.2: Screen Capture & Frozen Background
- Capture current screen state when overlay launches
- Display frozen screen as background in overlay
- Ensure cursor is visible in frozen capture
- Test background shows correctly

#### Block 4.3: Dark Overlay Layer
- Add 70% dark semi-transparent overlay
- Cover entire screen with darkened layer
- Test overlay opacity and visibility
- Ensure overlay doesn't interfere with events

#### Block 4.4: Window Highlighting System
- Detect window under cursor in real-time
- Add gray-white highlight overlay over detected window
- Update highlight as cursor moves between windows
- Clear highlight when cursor is on desktop

#### Block 4.5: Basic Mouse Event Handling
- Detect mouse clicks on overlay
- Distinguish between single clicks and drag starts
- Handle highlighted window click vs desktop click
- Add basic click position logging

#### Block 4.6: Enhanced Temporal Consistency Capture System
- **Enhanced upfront capture**: Capture full screen + all individual windows at overlay start
- **Temporal consistency**: All captures serve from the initial moment, no live recapture
- **Enhanced visual feedback**: Show actual window content instead of gray highlights
- **Pre-captured content serving**: Click handlers serve from stored captures

**Sub-blocks:**
- **Block 4.6a**: Enhanced screen state capture - capture all windows individually
- **Block 4.6b**: Enhanced window highlighting with actual content preview
- **Block 4.6c**: Serve pre-captured content for all user interactions

**Note**: Current window listing shows all workspaces - future optimization needed for current workspace filtering

#### Block 4.7: Selection Rectangle Drawing
- Implement click-and-drag rectangle creation
- Draw selection border (bright, 2px)
- Clear dark overlay within selection area
- Show actual screen content in selection

#### Block 4.8: Basic Magnifier Widget
- Create separate magnifier window (150x150px)
- Position magnifier near cursor
- Capture and display magnified area under cursor
- Test magnifier follows cursor movement

#### Block 4.9: Enhanced Magnifier Features
- Add 15-20x zoom magnification
- Implement pixel grid overlay
- Display current cursor coordinates (X, Y)
- Test magnifier accuracy and performance

#### Block 4.10: Selection Dimensions Display
- Show selection width x height in magnifier
- Update dimensions during drag operations
- Format dimension display clearly
- Test dimension accuracy

#### Block 4.11: Capture Integration & Polish
- Connect selection release to existing capture system
- Ensure clipboard and file saving work from overlay
- Add smooth overlay transitions
- Final testing and bug fixes

#### Block 4.12: Window Background Post-Processing
- Standardize window background handling across different window types
- Remove inconsistent borders and backgrounds from captured windows
- Implement intelligent background detection and removal
- Automatic border detection using edge analysis
- Smart content area identification and extraction
- Preserve actual window content while removing decoration artifacts

### Technical Architecture

**Enhanced Capture Flow:**
1. Overlay launches and captures frozen screen background (existing)
2. **NEW**: Immediately capture all visible windows individually using pure window capture
3. **NEW**: Store both full screen PIL image and individual window images with geometries
4. Dark overlay appears with real-time window content highlighting
5. User sees actual window content "pushed forward" when hovering
6. Click on highlighted window → serves pre-captured window image
7. Click on desktop → serves full screen image from initial capture
8. Drag → crops selection area from initial full screen capture

**Benefits:**
- Perfect temporal consistency - all captures from same moment
- WYSIWYG - users see exactly what they'll capture
- No live capture delays during interaction
- Enhanced visual feedback with actual content preview

**Technical Notes & Future Optimizations:**
- Window listing currently shows all workspaces, not just current workspace
- Future optimization: Filter windows by current workspace for better performance
- Memory optimization: Only capture windows that are actually visible in current workspace

**Overlay Window System:**
- Full-screen transparent PyQt6 window captures all mouse events
- **Enhanced upfront capture**: Frozen screen background + individual window captures at launch
- **Temporal consistency**: All user interactions serve from initial capture moment
- Dark overlay (70% opacity) covers entire screen
- **Enhanced window highlighting**: Shows actual captured window content instead of gray overlay
- Interactive drawing surface for UI elements

**Enhanced Capture Flow:**
1. Overlay launches and captures frozen screen background (existing)
2. **NEW**: Immediately capture all visible windows individually using pure window capture
3. **NEW**: Store both full screen PIL image and individual window images with geometries
4. Dark overlay appears with real-time window content highlighting
5. User sees actual window content "pushed forward" when hovering
6. Click on highlighted window → serves pre-captured window image
7. Click on desktop → serves full screen image from initial capture
8. Drag → crops selection area from initial full screen capture

**Benefits:**
- Perfect temporal consistency - all captures from same moment
- WYSIWYG - users see exactly what they'll capture
- No live capture delays during interaction
- Enhanced visual feedback with actual content preview

**User Experience Flow:**
1. Overlay launches with frozen screen background
2. Dark overlay appears with real-time window highlighting
3. User sees highlighted windows as cursor moves
4. Click on highlighted window → captures that window
5. Click on desktop → captures full screen
6. Drag → creates selection rectangle with magnifier

### Deliverables
- Complete interactive screenshot functionality with window highlighting
- Real-time visual feedback for window detection
- Working magnifier with pixel-perfect selection
- Smooth overlay interactions and immediate capture
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