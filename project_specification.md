# CaptiX - Full Specification (Updated)

## Overview
A fast, simple screenshot and screen recording tool for Linux X11. Optimized for speed and simplicity with pixel-perfect selection.

---

## Features

### 1. Screenshot Mode
**Trigger:** Ctrl+Shift+X (global hotkey, works everywhere) - configurable

**Flow:**
1. User presses Ctrl+Shift+X
2. Screen freezes (captures current display state)
3. Dark semi-transparent overlay appears over entire screen(s)
4. User can now interact:
   - **Single click on window**: Captures that window immediately
   - **Single click on desktop**: Captures full screen immediately
   - **Click and drag**: Creates selection rectangle

**Selection Interface (Drag Mode):**
- Mouse drag to create rectangular selection
- Selected area shows **actual screen content** (no overlay)
- Outside selection: **darkened/alpha overlay** (70% opacity)
- Selection rectangle has **visible border** (bright color, 2px)
- **Mouse release = capture immediately** (no resize, no confirmation)

**Pixel-Perfect Magnifier:**
- Small **zoom window** (150x150px) follows cursor during selection
- Shows **magnified view** of area around cursor (15-20x zoom)
- Displays **pixel grid** overlay on zoomed area
- Shows **current cursor position** in pixels (X, Y coordinates)
- Shows **selection dimensions** (Width x Height) when actively dragging
- Updates in real-time as cursor moves

**Controls:**
- **Escape**: Cancel and exit
- **Single click**: Capture window or full screen
- **Click and drag + release**: Capture selection

**Output:**
- Save to PNG: `~/Pictures/Screenshots/Screenshot_YYYY-MM-DD_HH-MM-SS.png`
- **Always copy to clipboard**
- **Always show notification**: "Screenshot saved! 2.4 MB" with actual file size

---

### 2. Video Recording Mode
**Trigger:** Super+Shift+X (global hotkey) - configurable

**Selection Flow:**
1. User presses Super+Shift+X
2. Same selection interface as screenshot mode appears
3. User interacts:
   - **Single click on window**: Records that window
   - **Single click on desktop**: Records full screen
   - **Click and drag + release**: Records selected area
4. Recording starts immediately after selection

**Recording Interface:**
A **floating control panel** appears (always on top):

```
┌─────────────────────────────────────┐
│ ● REC  00:02:47    ~127 MB         │
│                                     │
│ Recording: 1920x1080 (Full Screen) │
│                                     │
│  [■ Stop]     [✕ Abort]            │
└─────────────────────────────────────┘
```

**Control Panel Shows:**
- **Red recording indicator**: Pulsing red dot
- **Timer**: HH:MM:SS elapsed time
- **Estimated file size**: Calculated from duration × resolution × bitrate
- **Recording area info**: Resolution and type (Full Screen / Window / Custom Area)
- **Stop button**: Saves and finishes recording
- **Abort button**: Cancels recording, deletes file

**Recording Area Indicator:**
- If recording a specific area (not full screen):
  - Show semi-transparent **red border** around recorded area
  - Border stays visible during entire recording
  - **Border is static** (doesn't follow if window moves)

**Recording Settings (Fixed):**
- Format: **MP4** (H.264)
- FPS: **30**
- Audio: **System audio + microphone** (if microphone capture is easy to implement, otherwise system audio only)
- Resolution: **Full quality** (no downscaling)
- Cursor: **Always captured**

**Output:**
- Save to MP4: `~/Videos/Recordings/Recording_YYYY-MM-DD_HH-MM-SS.mp4`
- **Always show notification**: "Recording saved! Duration: 2:47 | 156.8 MB" with actual file size

---

## Technical Architecture

### Components

**1. Background Daemon** (`daemon.py`)
- Runs on startup (systemd user service)
- Reads hotkey configuration from config file
- Listens for global hotkeys using `pynput`:
  - Default Ctrl+Shift+X → launches screenshot mode
  - Default Super+Shift+X → launches video mode (or stops if recording)
- Spawns UI process when hotkey pressed
- Manages recording state (running/stopped)

**2. Screenshot UI** (`screenshot_ui.py`)
- Full-screen transparent overlay window (PyQt6 or GTK4)
- Captures frozen screen state on launch (with cursor visible)
- Handles three input modes:
  - Single click → detect window/desktop capture
  - Drag → draw selection rectangle
  - Mouse release → immediate capture
- Draws magnifier window during interaction
- Uses `python-xlib` for window detection
- Saves PNG, gets actual file size, copies to clipboard
- Shows notification with real file size via `notify-send` or DBus

**3. Video Recorder** (`video_recorder.py`)
- Same selection UI as screenshot
- After selection: spawns floating control panel
- Uses FFmpeg subprocess for encoding:
  ```bash
  # System audio only (simple)
  ffmpeg -f x11grab -r 30 -s 1920x1080 -i :0.0+100,100 \
         -f pulse -i default \
         -c:v libx264 -preset ultrafast -crf 23 \
         -c:a aac output.mp4
  
  # With microphone (if easy to implement)
  ffmpeg -f x11grab -r 30 -s 1920x1080 -i :0.0+100,100 \
         -f pulse -i default \
         -f pulse -i @DEFAULT_SOURCE@ \
         -filter_complex "[1:a][2:a]amix=inputs=2[a]" \
         -map 0:v -map "[a]" \
         -c:v libx264 -preset ultrafast -crf 23 \
         -c:a aac output.mp4
  ```
- Monitors file size in real-time (check actual file size on disk)
- Updates timer every second
- Draws static red border overlay if not full screen
- Stops on button click or second Super+Shift+X
- Gets final file size after encoding completes

**4. Main Entry Point** (`main.py`)
- Loads configuration file
- Handles command-line arguments:
  - `captix --daemon` → starts daemon
  - `captix --screenshot` → launches screenshot UI
  - `captix --video` → launches video UI
  - `captix --stop-recording` → stops active recording
- Routes to appropriate mode

### Tech Stack
- **Python 3.10+**
- **PyQt6**: UI framework (or GTK4 alternative)
- **python-xlib**: X11 screen capture and window detection
- **pynput**: Global hotkey listening
- **Pillow (PIL)**: Image manipulation and clipboard
- **FFmpeg** (system installed): Video/audio encoding with cursor capture
- **notify-send** or **python-dbus**: Desktop notifications

---

## UI Design

### Screenshot Selection Overlay
```
┌─────────────────────────────────────────┐
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│ ← Dark overlay (70%)
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│▓▓▓▓▓┌───────────────────┐▓▓▓▓▓▓▓▓▓▓▓▓▓▓│ ← Selection border
│▓▓▓▓▓│       ↖          │▓▓▓▓▓▓▓▓▓▓▓▓▓▓│ ← Cursor visible
│▓▓▓▓▓│   Clear area      │▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│▓▓▓▓▓│   (actual screen) │▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│▓▓▓▓▓│                   │▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│▓▓▓▓▓└───────────────────┘▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
└─────────────────────────────────────────┘

  ┌──────────────┐
  │ ╔══╦══╦══╗   │ ← Magnifier
  │ ╠══╬══╬══╣   │   (pixel grid)
  │ ╠══╬═╬╬══╣   │   (+ = cursor)
  │ ╚══╩══╩══╝   │
  │ X: 1847      │
  │ Y: 523       │
  │ 340 × 210    │ ← Dimensions
  └──────────────┘
```

### Video Recording Control Panel
```
┌──────────────────────────────────────────┐
│  ● REC   00:02:47        ~127 MB        │
│                                          │
│  Recording: 1920×1080 (Full Screen)     │
│                                          │
│   ┌──────────┐    ┌──────────┐         │
│   │ ■  Stop  │    │ ✕  Abort │         │
│   └──────────┘    └──────────┘         │
└──────────────────────────────────────────┘
```

### Recording Area Border (Static, Not Full Screen)
```
┌─────────────────────────────────────────┐
│                                         │
│    ╔═══════════════════════════╗       │ ← Red border
│    ║                           ║       │   (2-3px thick)
│    ║  This area is recording  ║       │   (semi-transparent)
│    ║  (border stays in place) ║       │   (static position)
│    ╚═══════════════════════════╝       │
│                                         │
└─────────────────────────────────────────┘
```

---

## File Structure
```
captix/
├── main.py                 # Entry point & CLI
├── daemon.py               # Hotkey listener daemon
├── screenshot_ui.py        # Screenshot overlay
├── video_recorder.py       # Video recording UI
├── recording_panel.py      # Floating control panel
├── utils/
│   ├── capture.py          # X11 screen/window capture (with cursor)
│   ├── window_detect.py    # Window under cursor detection
│   ├── magnifier.py        # Zoom window widget
│   ├── clipboard.py        # Clipboard operations
│   ├── notifications.py    # Desktop notifications
│   └── ffmpeg_wrapper.py   # FFmpeg process management
├── config.py               # Config file loader
├── requirements.txt        # Dependencies
├── setup.py                # PyInstaller config
├── captix.desktop          # Desktop entry
└── assets/
    ├── icon.png            # App icon
    └── captix.service      # Systemd service template
```

---

## User Experience Flow

### Screenshot:
1. **Press Ctrl+Shift+X** (anywhere - game, browser, IDE)
2. **Overlay appears** instantly (cursor visible)
3. **Option A:** Click on window → captures that window
4. **Option B:** Click on desktop → captures full screen
5. **Option C:** Drag area → captures on mouse release
6. **Notification appears:** "Screenshot saved! 2.4 MB"
7. **Image in clipboard** ready to paste
8. **File saved:** `~/Pictures/Screenshots/Screenshot_2025-09-29_14-32-45.png`

### Video Recording:
1. **Press Super+Shift+X**
2. **Select area** (click window/desktop or drag)
3. **Recording starts** with floating control panel
4. **Static red border** shows recorded area (if not full screen)
5. **Do whatever** needs recording (cursor visible in video)
6. **Press Super+Shift+X again** OR click Stop button
7. **Notification appears:** "Recording saved! Duration: 2:47 | 156.8 MB"
8. **File saved:** `~/Videos/Recordings/Recording_2025-09-29_14-32-45.mp4`

### Abort Recording:
- **Click Abort button** → recording cancelled, file deleted, notification shows "Recording aborted"

---

## Window Detection Logic

### Single Click Behavior:
```python
def handle_click(x, y):
    window = get_window_at_position(x, y)
    
    if window.is_root_window():
        # Clicked on desktop background
        capture_full_screen()
    else:
        # Clicked on actual window
        # Get window geometry (with decorations)
        geometry = get_window_geometry(window)
        capture_area(geometry.x, geometry.y, geometry.width, geometry.height)
```

**Window Frame Handling:**
- Always capture with decorations (title bar, borders) for consistency

---

## Configuration File
`~/.config/captix/config.json`:
```json
{
  "screenshot_dir": "~/Pictures/Screenshots",
  "video_dir": "~/Videos/Recordings",
  "video_fps": 30,
  "video_quality": 23,
  "notification_timeout": 5,
  "hotkeys": {
    "screenshot": "<ctrl>+<shift>+x",
    "video": "<super>+<shift>+x"
  }
}
```

**Hotkey Format:**
- Uses `pynput` key combination syntax
- Modifiers: `<ctrl>`, `<shift>`, `<alt>`, `<super>`
- Keys: lowercase letters, function keys, etc.
- Examples:
  - `<ctrl>+<shift>+x`
  - `<super>+<shift>+x`
  - `<print_screen>`
  - `<ctrl>+<shift>+<alt>+s`

**Config Loading:**
- Daemon reads config on startup
- If file doesn't exist, create with defaults
- User can edit and restart daemon to apply changes

---

## Installation & Setup

### PyInstaller Build:
```bash
pyinstaller --onefile --windowed \
  --name captix \
  --add-data "assets:assets" \
  main.py
```

### Systemd Service Install:
```bash
# Copy service file
cp captix.service ~/.config/systemd/user/

# Enable and start
systemctl --user enable captix.service
systemctl --user start captix.service
```

### Desktop Entry:
```ini
[Desktop Entry]
Name=CaptiX
Comment=Screenshot and screen recording tool
Exec=/usr/local/bin/captix --daemon
Icon=captix
Type=Application
Categories=Utility;Graphics;
StartupNotify=false
```

---

## Dependencies
```
PyQt6>=6.4.0          # UI framework
python-xlib>=0.33     # X11 access
pynput>=1.7.6         # Global hotkeys
Pillow>=10.0.0        # Image processing
notify2>=0.3.1        # Notifications
```

**System Requirements:**
- FFmpeg (for video recording with cursor capture)
- PulseAudio or PipeWire (for audio capture)
- X11 (not Wayland)

---

## FFmpeg Cursor Capture

X11grab includes cursor by default, but to ensure it:
```bash
# -draw_mouse 1 explicitly enables cursor capture
ffmpeg -f x11grab -draw_mouse 1 -r 30 -s 1920x1080 -i :0.0+100,100 \
       -f pulse -i default \
       -c:v libx264 -preset ultrafast -crf 23 \
       -c:a aac output.mp4
```

---

## Microphone Audio Implementation

**Simple approach (if PulseAudio/PipeWire):**
```python
# Check if microphone source exists
sources = subprocess.check_output(['pactl', 'list', 'short', 'sources'])
has_mic = b'@DEFAULT_SOURCE@' in sources or any microphone detected

if has_mic:
    # Use amix to combine system audio + mic
    ffmpeg_cmd = [
        'ffmpeg',
        '-f', 'x11grab', '-draw_mouse', '1', '-r', '30',
        '-s', f'{width}x{height}', '-i', f':0.0+{x},{y}',
        '-f', 'pulse', '-i', 'default',  # System audio
        '-f', 'pulse', '-i', '@DEFAULT_SOURCE@',  # Microphone
        '-filter_complex', '[1:a][2:a]amix=inputs=2[a]',
        '-map', '0:v', '-map', '[a]',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
        '-c:a', 'aac', output_file
    ]
else:
    # Fall back to system audio only
    ffmpeg_cmd = [...]  # System audio only version
```

**If this proves hassle:** Just use system audio only. Audio mixing can be added later.

---

## Key Design Principles
1. **Speed first**: No confirmation dialogs, capture on mouse release
2. **Simplicity**: Fixed settings, no option overload
3. **Always copy**: Clipboard integration by default
4. **Visual feedback**: Clear indicators for recording state, real file sizes
5. **Keyboard-friendly**: Configurable global hotkeys work everywhere
6. **X11 native**: Direct system access, no sandboxing overhead
7. **Cursor included**: Always captured in both screenshots and videos

---

This is CaptiX: Fast, simple, powerful screenshot and screen recording for Linux X11 with configurable hotkeys and cursor capture.