# CaptiX - Optional & Future Features

This document lists potential features and enhancements that could be implemented in the future. These are considered optional and are outside the scope of the core project specification.

---

## 1. Pinned Window Selection

### Description
When a user starts a drag-selection from *inside* a highlighted window, that window's pure content is "pinned" to the foreground. The user can then drag a selection rectangle that extends beyond the window's original boundaries. The final captured image would be a composite of the pinned window rendered on top of the frozen desktop background.

### User Benefit
- Allows a user to capture a specific window along with some of its surrounding desktop context, without other overlapping windows getting in the way.
- Creates a "spotlight" effect for a single window while still allowing for a larger area selection.

### Implementation Complexity
- **Moderate to High**.
- This requires a significant architectural change to the rendering logic. Instead of simply revealing a portion of a static background image, the application would need to dynamically compose a new image in memory (frozen background + pinned window) and use that as the source for the selection. This adds complexity and potential performance overhead.

---

## 2. Current Workspace Window Filtering

### Description
Modify the window detection system to only identify and highlight windows that exist on the currently active virtual desktop/workspace. The current implementation detects all windows across all workspaces.

### User Benefit
- **Performance:** Significantly speeds up the overlay initialization on systems with many open windows across multiple workspaces.
- **User Experience:** Prevents confusion by only showing selectable windows that are currently visible to the user.

### Implementation Complexity
- **Moderate**.
- Requires querying the window manager for the current workspace and then checking the `_NET_WM_DESKTOP` property for each window to filter them. This involves deeper integration with EWMH (Extended Window Manager Hints).

---

## 3. Basic Post-Capture Editor

### Description
After a screenshot is taken, instead of immediately saving, open a simple editor window. This editor would provide basic annotation tools:
- Rectangle/Ellipse
- Arrow
- Text
- Pen/Highlighter
- Crop
The user could then save, copy to clipboard, or discard the annotated image.

### User Benefit
- Adds immense value for communication and documentation, allowing users to quickly mark up screenshots without needing a separate application.

### Implementation Complexity
- **High**.
- This involves creating an entirely new, complex UI component for the editor. It would require managing tool states, drawing on a canvas, handling undo/redo, and integrating this new step into the capture workflow.

---

## 4. Configurable Video Settings

### Description
Expose key video recording settings in the `config.json` file, allowing users to override the fixed defaults.
- `video_fps` (e.g., 30, 60)
- `video_quality` (CRF value for libx264)
- `audio_source` (allow specifying a specific PulseAudio/PipeWire source)
- `encoder_preset` (e.g., `ultrafast`, `veryfast`, `medium`)

### User Benefit
- Gives advanced users control over the trade-off between file size, quality, and performance.
- Allows for higher FPS recording on powerful machines or selecting specific audio inputs.

### Implementation Complexity
- **Low to Moderate**.
- The main work involves reading these values from the config and safely incorporating them into the FFmpeg command string. Requires validation to prevent broken FFmpeg commands.

---

## 5. Wayland Support

### Description
Implement an alternative capture backend that uses the standard XDG Desktop Portals (`org.freedesktop.portal.Screenshot` and `org.freedesktop.portal.ScreenCast`) for Wayland compatibility. The application would need to detect the session type (X11 or Wayland) and call the appropriate backend.

### User Benefit
- Extends compatibility to modern Linux distributions that increasingly default to Wayland, where the current X11-based approach will not work.

### Implementation Complexity
- **Very High**.
- This is a major undertaking. It requires a completely different, asynchronous, DBus-based API for capturing. The portal-based approach offers less control over the UI, so the custom overlay would likely need to be replaced or heavily adapted to work with Wayland's security model. It's essentially writing a second, parallel capture system.