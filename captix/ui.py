#!/usr/bin/env python3
"""
CaptiX Screenshot UI - Interactive overlay for screenshot selection.

This module contains the PyQt6 implementation of the screenshot overlay.
It provides an interactive full-screen overlay with:
- Frozen background with window highlighting
- Area selection with live preview magnifier
- Window detection and pure content capture
- Real-time dimension display and crosshair guides

This module is imported and used by the captix.cli module.
Main entry point: captix/__main__.py or captix-screenshot wrapper script.

FAILSAFE MECHANISMS (Anti-hang protection):
1. External Watchdog - Separate process force-kills after 5s if frozen
2. Thread Watchdog - Background thread timeout after 5 seconds
"""

import sys
import os
import logging
import time
import threading
from typing import Optional, Dict
from dataclasses import dataclass
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import (
    Qt,
    QRect,
    QPropertyAnimation,
    QEasingCurve,
    pyqtProperty,
    QPoint,
    pyqtSignal,
    QTimer,
)
from PyQt6.QtGui import (
    QKeyEvent,
    QPaintEvent,
    QPainter,
    QColor,
    QPixmap,
    QMouseEvent,
    QImage,
)
from PIL import Image
from captix.utils.capture import ScreenCapture, list_visible_windows
from captix.utils.clipboard import copy_image_to_clipboard
from captix.utils.window_detect import WindowDetector, WindowInfo
from captix.utils.theme import CaptiXColors
from captix.utils.magnifier import MagnifierWidget
from captix.utils.notifications import notify_screenshot_saved, send_notification
from captix.utils.external_watchdog import ExternalWatchdog

# Set up logging
logging.basicConfig(level=logging.DEBUG)  # Enable debug logging
logger = logging.getLogger(__name__)

# Failsafe configuration
FAILSAFE_WATCHDOG_TIMEOUT_SECONDS = 5  # External watchdog timeout for complete freezes
FAILSAFE_THREAD_TIMEOUT_SECONDS = 5  # Max time for background thread operations


class UIConstants:
    """Configuration constants for screenshot UI overlay.

    These constants control the appearance and behavior of the interactive
    screenshot overlay, including animations, mouse interaction, and UI layout.
    """

    # Animation timing (milliseconds)
    FADE_ANIMATION_DURATION_MS = 250  # Window fade-in duration
    OVERLAY_OPACITY = 0.5  # Dark overlay opacity (50%)

    # Mouse interaction thresholds
    CLICK_THRESHOLD_MS = 200  # Max time for click vs drag (milliseconds)
    DRAG_THRESHOLD_PX = 5  # Min pixel movement to start drag
    WINDOW_DETECTION_MOVEMENT_PX = 10  # Min movement to trigger window detection

    # Window size filters (pixels)
    MIN_WINDOW_SIZE_CAPTURE = 200  # Minimum window size to capture
    MIN_WINDOW_SIZE_SYSTEM = 50  # Below this is likely a system window

    # UI layout (pixels)
    DIMENSIONS_DISPLAY_PADDING = 6  # Padding around dimension text
    DIMENSIONS_DISPLAY_MARGIN = 10  # Margin from selection edge
    HIGHLIGHT_BORDER_WIDTH = 2  # Window highlight border width

    # Timer intervals (milliseconds)
    WATCHDOG_CHECK_INTERVAL_MS = 1000  # How often to check watchdogs
    HEARTBEAT_UPDATE_INTERVAL_MS = 1000  # How often to update external watchdog


@dataclass
class CapturedWindow:
    """Stores a captured window with its metadata at capture time."""

    window_info: WindowInfo
    image: Image.Image  # PIL Image of just this window (content-only, borders excluded)
    qpixmap: Optional[QPixmap] = None  # Cached QPixmap for efficient rendering
    geometry: QRect = None  # Position/size at capture time (content-only)
    left_border: int = 0  # Left border size that was excluded
    top_border: int = 0  # Top border size that was excluded

    def __post_init__(self):
        """Initialize geometry from actual captured image dimensions and border offsets."""
        if self.geometry is None:
            # Use the actual image dimensions (content-only, borders excluded)
            content_width = self.image.width
            content_height = self.image.height

            # Adjust position using actual border offsets
            # The content starts at window position + border offset
            adjusted_x = self.window_info.x + self.left_border
            adjusted_y = self.window_info.y + self.top_border

            self.geometry = QRect(
                adjusted_x,
                adjusted_y,
                content_width,
                content_height,
            )


class ScreenshotOverlay(QWidget):
    """Full-screen transparent overlay for screenshot selection."""

    # Signal emitted when captures are complete
    captures_complete = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.frozen_screen: Optional[QPixmap] = None
        self.capture_system: Optional[ScreenCapture] = None
        self.window_detector: Optional[WindowDetector] = None
        self._overlay_opacity: float = 0.0  # Start with no opacity
        self.fade_animation: Optional[QPropertyAnimation] = None

        # Enhanced capture system
        self.captured_windows: Dict[
            int, CapturedWindow
        ] = {}  # window_id -> captured content
        self.frozen_full_image: Optional[Image.Image] = (
            None  # PIL version for area cutting
        )

        # Window highlighting state
        self.highlighted_window: Optional[WindowInfo] = None
        self.cursor_x: int = 0
        self.cursor_y: int = 0
        self.last_detection_pos: tuple = (-1, -1)  # Track last detection position

        # Mouse click tracking state
        self.mouse_pressed: bool = False
        self.press_start_time: float = 0.0
        self.press_position: tuple = (
            0,
            0,
        )  # Global coordinates where mouse was pressed
        self.click_threshold_ms: int = UIConstants.CLICK_THRESHOLD_MS  # Max time for click vs drag (milliseconds)
        self.drag_threshold_px: int = UIConstants.DRAG_THRESHOLD_PX  # Min pixel movement to start drag

        # Selection rectangle state
        self.is_dragging: bool = False
        self.current_drag_pos: tuple = (0, 0)  # Current mouse position during drag
        self.selection_rect: Optional[QRect] = None  # Current selection rectangle

        # Crosshair guideline state (QoL Feature)
        self.last_crosshair_pos: tuple = (-1, -1)  # Track last crosshair position

        # Window preview mode toggle (Right-click feature)
        self.is_preview_mode_enabled: bool = (
            False  # Default to False - only show border highlight
        )

        # Magnifier widget state
        self.magnifier: Optional[MagnifierWidget] = None

        # Failsafe timers
        self.thread_watchdog_timer: Optional[QTimer] = None
        self.thread_start_time: Optional[float] = None
        self.heartbeat_timer: Optional[QTimer] = None  # For external watchdog

        # External watchdog (works even if Qt event loop freezes)
        self.external_watchdog: Optional[ExternalWatchdog] = None

        self.setup_window()
        self.setup_failsafe_timers()

        # Initialize window detection BEFORE screen capture for proper filtering
        self.setup_window_detection()

        # Setup geometry and animation before captures for instant display
        self.setup_geometry()
        self.setup_animation()
        self.setup_magnifier()

        # Defer screen captures - will be done after window is shown
        self._captures_complete = False
        self._capture_lock = threading.Lock()

        # Thread Safety Design:
        # =====================
        # This overlay uses a read-after-initialization pattern for thread safety:
        #
        # 1. INITIALIZATION PHASE (background thread, protected by lock):
        #    - Background thread captures windows and populates captured_windows dict
        #    - All writes are protected by _capture_lock
        #    - Sets _captures_complete = True when done
        #    - Emits captures_complete signal to notify main thread
        #
        # 2. OPERATIONAL PHASE (main thread, no lock needed):
        #    - Main thread receives captures_complete signal
        #    - After signal, captured_windows becomes effectively read-only
        #    - No more writes from background thread
        #    - Main thread reads captured_windows without locks (safe after signal)
        #    - Python's GIL + signal/slot mechanism provides happens-before guarantee
        #
        # 3. CLEANUP PHASE (main thread, protected by lock):
        #    - captured_windows.clear() is protected by lock (defensive)
        #
        # This pattern avoids lock contention on every paint event while maintaining
        # thread safety. The lock is only needed during initialization and cleanup.

        # Connect signal for thread-safe capture completion
        self.captures_complete.connect(self._on_captures_complete)

    def setup_window(self):
        """Configure the overlay window properties."""
        # Make window frameless and always on top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        # Set window to be transparent
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Accept focus to receive key events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Enable mouse tracking to receive mouse move events
        self.setMouseTracking(True)

        # Set crosshair cursor for precision targeting
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Set window title for debugging
        self.setWindowTitle("CaptiX Screenshot Overlay")

        # Start with window opacity at 0 for fade-in effect
        self.setWindowOpacity(0.0)

        logger.debug("Overlay window configured")

    def capture_frozen_screen(self):
        """Capture the current screen state to use as frozen background (immediate, not in thread)."""
        try:
            logger.debug("Capturing frozen screen background...")

            # Initialize capture system
            self.capture_system = ScreenCapture()

            # Capture full screen with cursor (immediate)
            screen_image = self.capture_system.capture_full_screen(include_cursor=True)

            if screen_image:
                # Store the PIL version for area cutting
                self.frozen_full_image = screen_image.copy()

                # Convert PIL Image to QPixmap for background display
                # First convert PIL image to RGB if it's in RGBA mode
                if screen_image.mode == "RGBA":
                    # Create a white background and paste the image on it
                    background = Image.new("RGB", screen_image.size, (255, 255, 255))
                    background.paste(
                        screen_image, mask=screen_image.split()[-1]
                    )  # Use alpha channel as mask
                    screen_image = background
                elif screen_image.mode != "RGB":
                    screen_image = screen_image.convert("RGB")

                # Convert PIL image to bytes
                image_bytes = screen_image.tobytes()
                width, height = screen_image.size

                # Create QPixmap from image data
                # QImage format: RGB888 for 24-bit RGB
                qimage = QImage(image_bytes, width, height, QImage.Format.Format_RGB888)
                self.frozen_screen = QPixmap.fromImage(qimage)

                logger.info(f"Frozen screen captured: {width}x{height}")
            else:
                logger.error("Failed to capture screen for frozen background")

        except Exception as e:
            # Screen capture via PyQt6/X11 can fail for various reasons (display issues,
            # compositor problems, resource constraints). UI continues with degraded functionality.
            logger.error(f"Error capturing frozen screen: {e}")
            self.frozen_screen = None
            self.frozen_full_image = None

    def capture_all_windows(self):
        """Capture all visible windows individually with workspace filtering."""
        # Defensive check: prevent modifications after initialization complete
        if self._captures_complete:
            raise RuntimeError(
                "Cannot capture windows after initialization complete. "
                "This indicates a programming error - captures should only run during initialization."
            )

        try:
            logger.info(
                "Capturing visible windows with workspace and minimized filtering..."
            )

            # Get list of all visible windows
            all_visible_windows = list_visible_windows()

            # Apply workspace and minimized filtering
            if hasattr(self, "window_detector") and self.window_detector:
                filtered_windows = self.window_detector.filter_windows_for_capture(
                    all_visible_windows
                )
            else:
                # Fallback to basic filtering if no window detector available
                filtered_windows = [
                    w
                    for w in all_visible_windows
                    if not w.is_root and w.width >= UIConstants.MIN_WINDOW_SIZE_CAPTURE and w.height >= UIConstants.MIN_WINDOW_SIZE_CAPTURE
                ]
                logger.debug(
                    f"Using basic filtering: {len(filtered_windows)} out of {len(all_visible_windows)} windows"
                )

            captured_count = 0
            skipped_count = 0

            for window_info in filtered_windows:
                try:
                    # Additional skip check for very small windows (system windows)
                    if window_info.width < UIConstants.MIN_WINDOW_SIZE_SYSTEM and window_info.height < UIConstants.MIN_WINDOW_SIZE_SYSTEM:
                        logger.debug(
                            f"Skipping small window: {window_info.title} ({window_info.width}x{window_info.height})"
                        )
                        skipped_count += 1
                        continue

                    # Capture this window's pure content without cursor
                    result = self.capture_system.capture_window_pure_content(
                        window_info.window_id, include_cursor=False
                    )

                    if result:
                        # Unpack the result tuple (image, left_border, top_border)
                        window_image, left_border, top_border = result

                        # Store the captured window with border information
                        captured_window = CapturedWindow(
                            window_info=window_info,
                            image=window_image,
                            left_border=left_border,
                            top_border=top_border,
                        )

                        self.captured_windows[window_info.window_id] = captured_window
                        captured_count += 1

                        logger.debug(
                            f"Captured window: {window_info.title} ({window_info.class_name}) "
                            f"{window_info.width}x{window_info.height}"
                        )
                    else:
                        logger.debug(f"Failed to capture window: {window_info.title}")
                        skipped_count += 1

                except Exception as e:
                    logger.warning(f"Error capturing window {window_info.title}: {e}")
                    skipped_count += 1
                    continue

            logger.info(
                f"Window capture complete: {captured_count} captured, {skipped_count} skipped"
            )

        except Exception as e:
            logger.error(f"Error capturing windows: {e}")
            # Continue with empty captured windows dict - overlay will still work with basic highlighting

    def get_window_qpixmap(self, window_id: int) -> Optional[QPixmap]:
        """Get or create QPixmap for a captured window for efficient rendering."""
        if window_id not in self.captured_windows:
            return None

        captured_window = self.captured_windows[window_id]

        # Return cached QPixmap if available
        if captured_window.qpixmap is not None:
            return captured_window.qpixmap

        # Convert PIL image to QPixmap and cache it
        try:
            pil_image = captured_window.image

            # Handle alpha channel properly to avoid white borders
            if pil_image.mode == "RGBA":
                # Instead of white background, use transparent background
                # or convert more carefully to preserve the original look

                # Option 1: Convert RGBA directly to QImage to preserve alpha
                width, height = pil_image.size
                image_bytes = pil_image.tobytes()
                bytes_per_line = width * 4  # 4 bytes per pixel for RGBA

                qimage = QImage(
                    image_bytes,
                    width,
                    height,
                    bytes_per_line,
                    QImage.Format.Format_RGBA8888,
                )
                qpixmap = QPixmap.fromImage(qimage)

            elif pil_image.mode != "RGB":
                # Convert other modes to RGB
                pil_image = pil_image.convert("RGB")
                width, height = pil_image.size
                image_bytes = pil_image.tobytes()
                bytes_per_line = width * 3  # 3 bytes per pixel for RGB

                qimage = QImage(
                    image_bytes,
                    width,
                    height,
                    bytes_per_line,
                    QImage.Format.Format_RGB888,
                )
                qpixmap = QPixmap.fromImage(qimage)
            else:
                # Already RGB format
                width, height = pil_image.size
                image_bytes = pil_image.tobytes()
                bytes_per_line = width * 3  # 3 bytes per pixel for RGB

                qimage = QImage(
                    image_bytes,
                    width,
                    height,
                    bytes_per_line,
                    QImage.Format.Format_RGB888,
                )
                qpixmap = QPixmap.fromImage(qimage)

            # Cache the QPixmap for future use
            captured_window.qpixmap = qpixmap

            logger.debug(
                f"Created QPixmap for window {window_id}: {width}x{height} ({pil_image.mode})"
            )
            return qpixmap

        except Exception as e:
            logger.warning(f"Failed to convert window {window_id} to QPixmap: {e}")
            return None

    def setup_geometry(self):
        """Prepare window for fullscreen mode."""
        app = QApplication.instance()
        if not app:
            logger.error("No QApplication instance found")
            return

        # Get all screens for logging purposes
        screens = app.screens()
        if screens:
            # Calculate combined geometry of all screens for logging
            combined_rect = QRect()
            for screen in screens:
                screen_geometry = screen.geometry()
                logger.info(
                    f"Screen found: {screen_geometry.width()}x{screen_geometry.height()} at ({screen_geometry.x()}, {screen_geometry.y()})"
                )
                combined_rect = combined_rect.united(screen_geometry)

            logger.info(
                f"Overlay prepared for fullscreen mode covering: {combined_rect.width()}x{combined_rect.height()}"
            )
        else:
            logger.error("No screens found")

    def setup_animation(self):
        """Set up the fade-in animation for the window and dark overlay."""
        # Create animation for the window opacity (entire window fades in)
        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(UIConstants.FADE_ANIMATION_DURATION_MS)  # 0.25 seconds
        self.fade_animation.setStartValue(0.0)  # Start transparent
        self.fade_animation.setEndValue(1.0)  # End fully visible
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Set the dark overlay to target opacity immediately (no separate animation)
        self._overlay_opacity = UIConstants.OVERLAY_OPACITY

        logger.debug("Fade animation configured (0.25s, window opacity 0% to 100%)")

    def setup_window_detection(self):
        """Initialize window detection system."""
        try:
            self.window_detector = WindowDetector()
            # Get our overlay window ID to exclude it from detection
            self.overlay_window_id = int(self.winId())
            logger.info(
                f"Window detection system initialized, overlay window ID: {self.overlay_window_id}"
            )
        except Exception as e:
            # Window detection initialization can fail due to X11 errors, missing libraries,
            # or incompatible window managers. App continues without window detection features.
            logger.error(f"Failed to initialize window detection: {e}")
            self.window_detector = None
            self.overlay_window_id = None

    def setup_magnifier(self):
        """Initialize the magnifier widget."""
        try:
            self.magnifier = MagnifierWidget()
            logger.info(f"Magnifier widget initialized ({MagnifierWidget.MAGNIFIER_SIZE}x{MagnifierWidget.MAGNIFIER_SIZE}px)")
        except Exception as e:
            logger.error(f"Failed to initialize magnifier widget: {e}")
            self.magnifier = None

    def setup_failsafe_timers(self):
        """Initialize all failsafe timers and watchdogs."""
        # Thread watchdog timer - monitors background thread execution
        self.thread_watchdog_timer = QTimer(self)
        self.thread_watchdog_timer.timeout.connect(self._on_thread_watchdog)
        self.thread_watchdog_timer.start(UIConstants.WATCHDOG_CHECK_INTERVAL_MS)  # Check every second
        logger.debug(f"Thread watchdog failsafe enabled: {FAILSAFE_THREAD_TIMEOUT_SECONDS}s max thread time")

        # External watchdog - CRITICAL: This works even if Qt event loop freezes
        try:
            self.external_watchdog = ExternalWatchdog(timeout_seconds=FAILSAFE_WATCHDOG_TIMEOUT_SECONDS)
            self.external_watchdog.start_watchdog(pid_to_monitor=os.getpid())

            # Heartbeat timer - updates external watchdog that we're still alive
            self.heartbeat_timer = QTimer(self)
            self.heartbeat_timer.timeout.connect(self._update_external_watchdog_heartbeat)
            self.heartbeat_timer.start(UIConstants.HEARTBEAT_UPDATE_INTERVAL_MS)  # Update every 1 second
            logger.info(f"External watchdog failsafe enabled: {FAILSAFE_WATCHDOG_TIMEOUT_SECONDS}s freeze detection")
        except Exception as e:
            logger.error(f"Failed to start external watchdog: {e}")

    def _update_external_watchdog_heartbeat(self):
        """Update the external watchdog heartbeat to signal we're still responsive."""
        if self.external_watchdog:
            try:
                heartbeat_start = time.perf_counter()
                self.external_watchdog.update_heartbeat()
                heartbeat_time = time.perf_counter() - heartbeat_start

                # Log heartbeat updates (at debug level) to track event loop health
                logger.debug(f"[HEARTBEAT] Watchdog heartbeat updated ({heartbeat_time*1000:.1f}ms)")

                # Warn if heartbeat update itself is slow (file I/O should be fast)
                if heartbeat_time > 0.010:
                    logger.warning(
                        f"[HEARTBEAT] Heartbeat update took {heartbeat_time*1000:.1f}ms - I/O may be slow"
                    )
            except (OSError, IOError) as e:
                logger.warning(f"[HEARTBEAT] Failed to update watchdog heartbeat: {e}")

    def _on_thread_watchdog(self):
        """Monitor background thread and force exit if it hangs."""
        if self.thread_start_time is not None and not self._captures_complete:
            elapsed = time.time() - self.thread_start_time
            if elapsed >= FAILSAFE_THREAD_TIMEOUT_SECONDS:
                logger.warning(
                    f"FAILSAFE: Background thread timeout after {elapsed:.1f}s - forcing exit"
                )
                # Show notification
                try:
                    send_notification(
                        "Thread Timeout",
                        "Screenshot overlay closed due to hung background operation",
                        urgency="critical"
                    )
                except Exception as e:
                    logger.warning(f"Failed to show thread timeout notification: {e}")
                self._force_exit("Thread timeout")

    def _force_exit(self, reason: str = "Emergency exit"):
        """Force immediate exit of the overlay with cleanup."""
        logger.warning(f"FORCE EXIT triggered: {reason}")
        try:
            # Stop all timers immediately
            # Note: auto_timeout_timer was removed in commit a46a066 (redundant failsafe)
            if self.thread_watchdog_timer:
                self.thread_watchdog_timer.stop()
            if self.fade_animation:
                self.fade_animation.stop()

            # Hide magnifier (best effort during emergency cleanup)
            if self.magnifier:
                try:
                    self.magnifier.hide_magnifier()
                    self.magnifier.close()
                except Exception:
                    # Intentionally silenced - magnifier cleanup is best-effort during emergency exit
                    # Any errors are caught and logged by the outer exception handler below
                    pass

            # Force close window
            self.close()

            # Quit application
            app = QApplication.instance()
            if app:
                app.quit()

        except Exception as e:
            logger.error(f"Error during force exit: {e}")
            # Last resort - call os._exit to terminate immediately
            import os
            os._exit(1)

    def update_window_highlight(self, x: int, y: int):
        """Update window highlighting based on cursor position."""
        if not self.window_detector:
            return

        # Store cursor position
        self.cursor_x = x
        self.cursor_y = y

        # Only update detection if cursor moved significantly (reduce frequency)
        distance_moved = abs(x - self.last_detection_pos[0]) + abs(
            y - self.last_detection_pos[1]
        )
        if distance_moved < UIConstants.WINDOW_DETECTION_MOVEMENT_PX:  # Only detect every 10 pixels of movement
            return

        self.last_detection_pos = (x, y)

        try:
            # Get window beneath our overlay using stack walking
            # Add timing to detect if X11 calls are blocking
            detection_start = time.perf_counter()
            window_info = self.window_detector.get_window_at_position_excluding(
                x, y, exclude_window_id=getattr(self, "overlay_window_id", None)
            )
            detection_time = time.perf_counter() - detection_start

            # Log if window detection is slow (>100ms could freeze event loop)
            if detection_time > 0.100:
                logger.warning(
                    f"[PERF] Window detection at ({x},{y}) took {detection_time*1000:.1f}ms - potential hang risk!"
                )
            elif detection_time > 0.050:
                logger.debug(
                    f"[PERF] Window detection at ({x},{y}) took {detection_time*1000:.1f}ms"
                )

            # Debug: Log the detected window information (only when it changes)
            if window_info != self.highlighted_window:
                if window_info:
                    logger.info(
                        f"Detected window at {x},{y}: {window_info.title} ({window_info.class_name}) "
                        f"size: {window_info.width}x{window_info.height} at {window_info.x},{window_info.y} "
                        f"is_root: {window_info.is_root}"
                    )
                else:
                    logger.info(f"No window detected at {x},{y}")

            # Only update if the window changed
            if window_info != self.highlighted_window:
                self.highlighted_window = window_info

                if window_info and not window_info.is_root:
                    logger.debug(
                        f"Highlighting window: {window_info.title} ({window_info.class_name}) "
                        f"at {window_info.x},{window_info.y} {window_info.width}x{window_info.height}"
                    )
                else:
                    logger.debug("Cursor on desktop - clearing highlight")

                # Trigger repaint to update highlight
                self.update()

        except Exception as e:
            logger.error(f"Error updating window highlight: {e}")
            self.highlighted_window = None

    def update_selection_rectangle(self):
        """Update the selection rectangle based on current drag positions."""
        if not self.is_dragging:
            self.selection_rect = None
            return

        # Calculate rectangle from press position to current drag position
        x1, y1 = self.press_position
        x2, y2 = self.current_drag_pos

        # Create rectangle with top-left and bottom-right coordinates
        left = min(x1, x2)
        top = min(y1, y2)
        right = max(x1, x2)
        bottom = max(y1, y2)

        # Convert to global screen coordinates to QRect
        self.selection_rect = QRect(left, top, right - left, bottom - top)

        logger.debug(
            f"Selection rectangle updated: {self.selection_rect.width()}x{self.selection_rect.height()} "
            f"at ({self.selection_rect.x()}, {self.selection_rect.y()})"
        )

    @pyqtProperty(float)
    def overlay_opacity(self) -> float:
        """Get the current overlay opacity (0.0 to 1.0)."""
        return self._overlay_opacity

    @overlay_opacity.setter
    def overlay_opacity(self, value: float):
        """Set the overlay opacity and trigger a repaint."""
        self._overlay_opacity = value
        self.update()  # Trigger paintEvent

    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            logger.info("Escape key pressed - closing overlay")
            # Exit the application when overlay is closed
            app = QApplication.instance()
            if app:
                app.quit()
            self.close()
        else:
            # Pass other keys to parent
            super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move events for window highlighting and drag selection."""
        # Performance timing to detect slow mouse handlers
        mouse_start = time.perf_counter()

        # Convert local coordinates to global screen coordinates
        global_pos = self.mapToGlobal(event.position().toPoint())

        # Always update cursor position for crosshair guidelines
        self.cursor_x = global_pos.x()
        self.cursor_y = global_pos.y()

        logger.debug(f"[MOUSE] Move event at ({self.cursor_x}, {self.cursor_y}), pressed={self.mouse_pressed}, dragging={self.is_dragging}")

        # Check if this might be the start of a drag operation
        if self.mouse_pressed and not self.is_dragging:
            current_pos = (global_pos.x(), global_pos.y())
            distance_moved = abs(current_pos[0] - self.press_position[0]) + abs(
                current_pos[1] - self.press_position[1]
            )

            if distance_moved >= self.drag_threshold_px:
                logger.info(
                    f"Drag started: moved {distance_moved}px from press position"
                )
                self.is_dragging = True
                # Clear window highlighting when dragging starts
                self.highlighted_window = None

        # Always update magnifier position during cursor movement
        if self.magnifier and self.frozen_screen:
            self.magnifier.set_source_image(self.frozen_screen)
            self.magnifier.update_cursor_position(global_pos.x(), global_pos.y())
            self.magnifier.show_magnifier()

        # Handle active dragging
        if self.is_dragging:
            current_pos = (global_pos.x(), global_pos.y())
            self.current_drag_pos = current_pos

            # Update selection rectangle
            self.update_selection_rectangle()

            # Trigger repaint to show selection rectangle and crosshair guidelines
            self.update()
        else:
            # Update window highlighting when not dragging
            self.update_window_highlight(global_pos.x(), global_pos.y())

        # Update crosshair guidelines if cursor moved (reduce repaint frequency)
        current_crosshair_pos = (self.cursor_x, self.cursor_y)
        if current_crosshair_pos != self.last_crosshair_pos:
            self.last_crosshair_pos = current_crosshair_pos
            self.update()  # Repaint for crosshair guidelines

        # Log if mouse event handling was slow
        mouse_time = time.perf_counter() - mouse_start
        if mouse_time > 0.050:
            logger.warning(f"[PERF] mouseMoveEvent took {mouse_time*1000:.1f}ms - potential hang risk!")
        elif mouse_time > 0.016:
            logger.debug(f"[PERF] mouseMoveEvent took {mouse_time*1000:.1f}ms")

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events - start of click or drag."""
        logger.debug(f"[MOUSE] Press event: button={event.button()}")

        if event.button() == Qt.MouseButton.LeftButton:
            # Convert to global coordinates
            global_pos = self.mapToGlobal(event.position().toPoint())

            # Record press details
            self.mouse_pressed = True
            self.press_start_time = time.time()
            self.press_position = (global_pos.x(), global_pos.y())

            logger.debug(f"[MOUSE] Left button pressed at global position: {self.press_position}")

            # Check what's under the cursor at press time
            if self.highlighted_window:
                if self.highlighted_window.is_root:
                    logger.debug("Mouse pressed on desktop/root window")
                else:
                    logger.debug(
                        f"Mouse pressed on window: {self.highlighted_window.title} ({self.highlighted_window.class_name})"
                    )
            else:
                logger.debug("Mouse pressed with no window detected")

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release events - complete click or end drag."""
        # Handle right-click to toggle window preview mode
        if event.button() == Qt.MouseButton.RightButton:
            self.is_preview_mode_enabled = not self.is_preview_mode_enabled
            logger.info(
                f"Window preview mode toggled to: {'ON' if self.is_preview_mode_enabled else 'OFF'}"
            )
            self.update()  # Trigger a repaint to reflect the new state
            return

        # Handle left-click events (existing logic)
        if event.button() == Qt.MouseButton.LeftButton and self.mouse_pressed:
            # Convert to global coordinates
            global_pos = self.mapToGlobal(event.position().toPoint())
            current_pos = (global_pos.x(), global_pos.y())

            # Calculate click duration and movement
            click_duration_ms = (time.time() - self.press_start_time) * 1000
            distance_moved = abs(current_pos[0] - self.press_position[0]) + abs(
                current_pos[1] - self.press_position[1]
            )

            # Reset mouse state
            self.mouse_pressed = False
            self.is_dragging = False
            self.selection_rect = None

            # Hide magnifier on mouse release
            if self.magnifier:
                self.magnifier.hide_magnifier()

            logger.debug(
                f"Mouse released at {current_pos}, duration: {click_duration_ms:.1f}ms, moved: {distance_moved}px"
            )

            # Determine click type and handle accordingly
            # It's a click if EITHER duration is quick OR movement is minimal
            if (
                click_duration_ms <= self.click_threshold_ms
                or distance_moved < self.drag_threshold_px
            ):
                # This is a single click - convert position to QPoint
                click_pos = QPoint(self.press_position[0], self.press_position[1])
                self.handle_single_click(click_pos)
            else:
                # This was a drag operation
                self.handle_drag_complete(self.press_position, current_pos)

        super().mouseReleaseEvent(event)

    def handle_single_click(self, pos: QPoint):
        """Handle single click for window or desktop capture using pre-captured content."""
        try:
            # Use the window that was detected during mouse press
            if self.highlighted_window and not self.highlighted_window.is_root:
                # Window was clicked - find the corresponding captured window
                target_window_id = self.highlighted_window.window_id

                if target_window_id in self.captured_windows:
                    captured_window = self.captured_windows[target_window_id]
                    logger.debug(
                        f"Window click detected on: {captured_window.window_info.title}"
                    )

                    if captured_window.image:
                        # Use pre-captured window content and existing save infrastructure
                        try:
                            filepath, file_size = self.capture_system.save_screenshot(
                                captured_window.image, capture_type="win"
                            )
                            # Copy to clipboard using existing infrastructure
                            if copy_image_to_clipboard(filepath):
                                logger.info(
                                    f"Window capture completed: {captured_window.window_info.title} ({file_size} bytes)"
                                )
                            else:
                                logger.warning(
                                    "Failed to copy window capture to clipboard"
                                )
                            # Show notification with sound
                            try:
                                notify_screenshot_saved(filepath, file_size)
                            except Exception as e:
                                logger.warning(f"Failed to show notification: {e}")
                        except (OSError, IOError, PermissionError) as e:
                            logger.error(f"Failed to save window capture for '{captured_window.window_info.title}': {e}")
                    else:
                        logger.warning(
                            f"No image available for window: {captured_window.window_info.title}"
                        )
                else:
                    logger.warning(
                        f"Clicked window (ID: {target_window_id}) not found in captured windows"
                    )
                    # Fall back to desktop capture
                    self._capture_desktop()
            else:
                # No window clicked or desktop clicked - capture full desktop using frozen image
                self._capture_desktop()

            self.close()

        except Exception as e:
            logger.error(f"Error in handle_single_click: {e}")
            self.close()

    def _capture_desktop(self):
        """Helper method to capture desktop using frozen image."""
        logger.info("Desktop click detected - capturing full screen")
        if self.frozen_full_image:
            # Use pre-captured desktop content and existing save infrastructure
            try:
                filepath, file_size = self.capture_system.save_screenshot(
                    self.frozen_full_image, capture_type="full"
                )
                # Copy to clipboard using existing infrastructure
                if copy_image_to_clipboard(filepath):
                    logger.info(f"Full desktop capture completed ({file_size} bytes)")
                else:
                    logger.warning("Failed to copy desktop capture to clipboard")
                # Show notification with sound
                try:
                    notify_screenshot_saved(filepath, file_size)
                except Exception as e:
                    logger.warning(f"Failed to show notification: {e}")
            except (OSError, IOError, PermissionError) as e:
                logger.error(f"Failed to save desktop capture: {e}")
        else:
            logger.error("No frozen desktop image available")

    def handle_drag_complete(self, start_pos: tuple, end_pos: tuple):
        """Handle completed drag selection for area capture using pre-captured content."""
        try:
            x1, y1 = start_pos
            x2, y2 = end_pos

            # Calculate selection rectangle
            left = min(x1, x2)
            top = min(y1, y2)
            right = max(x1, x2)
            bottom = max(y1, y2)

            width = right - left
            height = bottom - top

            # Validate selection area
            if width <= 0 or height <= 0:
                logger.warning("Invalid selection area - no capture performed")
                self.close()
                return

            logger.info(
                f"Area selection: ({left}, {top}) to ({right}, {bottom}) - {width}x{height}"
            )

            # Use pre-captured desktop content for cropping
            if self.frozen_full_image:
                # Crop the selected area from frozen image
                # Add 1 pixel to right and bottom to include the current selected pixel
                try:
                    cropped_image = self.frozen_full_image.crop(
                        (left, top, right + 1, bottom + 1)
                    )
                    # Use existing save infrastructure
                    filepath, file_size = self.capture_system.save_screenshot(
                        cropped_image, capture_type="area"
                    )
                    # Copy to clipboard using existing infrastructure
                    if copy_image_to_clipboard(filepath):
                        logger.info(
                            f"Area capture completed: {width}x{height} pixels ({file_size} bytes)"
                        )
                    else:
                        logger.warning("Failed to copy area capture to clipboard")
                    # Show notification with sound
                    try:
                        notify_screenshot_saved(filepath, file_size)
                    except Exception as e:
                        logger.warning(f"Failed to show notification: {e}")
                except (OSError, IOError, PermissionError) as e:
                    logger.error(f"Failed to save area capture ({width}x{height} pixels): {e}")
            else:
                logger.error("No frozen desktop image available for area capture")

            self.close()

        except Exception as e:
            logger.error(f"Error in handle_drag_complete: {e}")
            self.close()

    def _draw_frozen_background(self, painter: QPainter):
        """Draw the frozen screen background or fallback."""
        if self.frozen_screen:
            painter.drawPixmap(self.rect(), self.frozen_screen, self.frozen_screen.rect())
            logger.debug("Frozen screen background drawn")
        else:
            painter.fillRect(self.rect(), QColor(128, 128, 128, 50))
            logger.warning("No frozen screen available, using fallback background")

    def _calculate_exclusion_rect(self) -> Optional[QRect]:
        """Calculate area to exclude from dark overlay (selection or highlighted window)."""
        if self.selection_rect and self.is_dragging:
            return self.selection_rect
        elif self.highlighted_window and not self.highlighted_window.is_root and not self.is_dragging:
            if self.highlighted_window.window_id in self.captured_windows:
                window_geometry = self.captured_windows[self.highlighted_window.window_id].geometry
            else:
                window_geometry = self._get_window_content_geometry(self.highlighted_window)
            return window_geometry.intersected(self.rect())
        return None

    def _draw_overlay_around_exclusion(self, painter: QPainter, color: QColor, exclusion_rect: QRect):
        """Draw overlay in 4 regions around the exclusion rectangle."""
        screen_rect = self.rect()

        # Top region (above exclusion)
        if exclusion_rect.top() > screen_rect.top():
            top_rect = QRect(
                screen_rect.left(),
                screen_rect.top(),
                screen_rect.width(),
                exclusion_rect.top() - screen_rect.top(),
            )
            painter.fillRect(top_rect, color)

        # Bottom region (below exclusion)
        if exclusion_rect.bottom() < screen_rect.bottom():
            bottom_rect = QRect(
                screen_rect.left(),
                exclusion_rect.bottom(),
                screen_rect.width(),
                screen_rect.bottom() - exclusion_rect.bottom(),
            )
            painter.fillRect(bottom_rect, color)

        # Left region (left of exclusion)
        if exclusion_rect.left() > screen_rect.left():
            left_rect = QRect(
                screen_rect.left(),
                max(screen_rect.top(), exclusion_rect.top()),
                exclusion_rect.left() - screen_rect.left(),
                min(screen_rect.bottom(), exclusion_rect.bottom())
                - max(screen_rect.top(), exclusion_rect.top()),
            )
            painter.fillRect(left_rect, color)

        # Right region (right of exclusion)
        if exclusion_rect.right() < screen_rect.right():
            right_rect = QRect(
                exclusion_rect.right(),
                max(screen_rect.top(), exclusion_rect.top()),
                screen_rect.right() - exclusion_rect.right(),
                min(screen_rect.bottom(), exclusion_rect.bottom())
                - max(screen_rect.top(), exclusion_rect.top()),
            )
            painter.fillRect(right_rect, color)

    def _draw_selection_border(self, painter: QPainter):
        """Draw selection border based on drag direction."""
        pen = painter.pen()
        pen.setColor(CaptiXColors.THEME_BLUE)
        pen.setWidth(UIConstants.HIGHLIGHT_BORDER_WIDTH)
        pen.setStyle(Qt.PenStyle.DashDotLine)
        painter.setPen(pen)

        # Get selection rectangle bounds
        left = self.selection_rect.left()
        right = self.selection_rect.right()
        top = self.selection_rect.top()
        bottom = self.selection_rect.bottom()

        # Get drag origin and current cursor position
        origin_x, origin_y = self.press_position
        cursor_x, cursor_y = self.cursor_x, self.cursor_y

        # Draw borders based on drag direction
        if cursor_y < origin_y:
            painter.drawLine(left, bottom, right, bottom)
        if cursor_y > origin_y:
            painter.drawLine(left, top, right, top)
        if cursor_x < origin_x:
            painter.drawLine(right, top, right, bottom)
        if cursor_x > origin_x:
            painter.drawLine(left, top, left, bottom)

        # Draw dimensions display
        self.draw_selection_dimensions(painter)

        logger.debug(
            f"Selection rectangle drawn: {self.selection_rect.width()}x{self.selection_rect.height()} "
            f"at ({self.selection_rect.x()}, {self.selection_rect.y()})"
        )

    def _draw_dark_overlay_with_selection(self, painter: QPainter):
        """Draw dark overlay everywhere except selection/highlighted window, and draw selection border."""
        # Calculate alpha and color
        alpha_value = int(self._overlay_opacity * 255)
        dark_overlay_color = CaptiXColors.DARK_OVERLAY_BLACK
        dark_overlay_color.setAlpha(alpha_value)

        # Determine exclusion rectangle
        exclusion_rect = self._calculate_exclusion_rect()

        if exclusion_rect and not exclusion_rect.isEmpty():
            # Draw overlay in 4 regions around exclusion
            self._draw_overlay_around_exclusion(painter, dark_overlay_color, exclusion_rect)

            # Draw selection border if dragging
            if self.selection_rect and self.is_dragging:
                self._draw_selection_border(painter)
        else:
            # No exclusion - draw overlay over entire screen
            painter.fillRect(self.rect(), dark_overlay_color)

        if alpha_value > 0:
            logger.debug(f"Dark overlay layer drawn ({self._overlay_opacity:.1%} opacity, alpha={alpha_value})")

    def paintEvent(self, event: QPaintEvent):
        """Paint the overlay with frozen screen background, dark overlay, selection rectangle, and window highlight."""
        # Performance timing for hang diagnosis
        paint_start = time.perf_counter()

        painter = QPainter(self)

        # Draw background
        bg_start = time.perf_counter()
        self._draw_frozen_background(painter)
        bg_time = time.perf_counter() - bg_start

        # Draw dark overlay with exclusion logic
        overlay_start = time.perf_counter()
        self._draw_dark_overlay_with_selection(painter)
        overlay_time = time.perf_counter() - overlay_start

        # Draw window highlight (only when not dragging)
        alpha_value = int(self._overlay_opacity * 255)
        highlight_time = 0
        if (
            self.highlighted_window
            and not self.highlighted_window.is_root
            and alpha_value > 0
            and not self.is_dragging
        ):
            highlight_start = time.perf_counter()
            self.draw_window_highlight(painter)
            highlight_time = time.perf_counter() - highlight_start

        # Draw crosshair guidelines
        crosshair_start = time.perf_counter()
        self.draw_crosshair_guidelines(painter)
        crosshair_time = time.perf_counter() - crosshair_start

        # Log performance if paint took too long (>50ms could indicate issues)
        total_time = time.perf_counter() - paint_start
        if total_time > 0.050:
            logger.warning(
                f"[PERF] paintEvent took {total_time*1000:.1f}ms "
                f"(bg:{bg_time*1000:.1f}ms, overlay:{overlay_time*1000:.1f}ms, "
                f"highlight:{highlight_time*1000:.1f}ms, crosshair:{crosshair_time*1000:.1f}ms)"
            )
        elif total_time > 0.016:  # More than one frame at 60fps
            logger.debug(
                f"[PERF] paintEvent took {total_time*1000:.1f}ms "
                f"(bg:{bg_time*1000:.1f}ms, overlay:{overlay_time*1000:.1f}ms, "
                f"highlight:{highlight_time*1000:.1f}ms, crosshair:{crosshair_time*1000:.1f}ms)"
            )

    def draw_window_highlight(self, painter: QPainter):
        """Draw highlight overlay over the currently highlighted window."""
        window = self.highlighted_window
        if not window:
            return

        # Use captured window geometry if available (content-only, borders excluded)
        # Otherwise calculate content-only geometry immediately using border detection
        if window.window_id in self.captured_windows:
            original_window_rect = self.captured_windows[window.window_id].geometry
        else:
            # Calculate content-only geometry immediately using border detection
            original_window_rect = self._get_window_content_geometry(window)

        # Calculate visible portion within screen bounds
        screen_rect = self.rect()
        visible_window_rect = original_window_rect.intersected(screen_rect)

        if visible_window_rect.isEmpty():
            return

        # Conditional rendering based on preview mode
        if self.is_preview_mode_enabled:
            # Preview ON: Show full window content (bring-to-front effect)
            # Try to show actual captured window content instead of gray overlay
            window_pixmap = self.get_window_qpixmap(window.window_id)

            if window_pixmap:
                # Calculate which part of the captured image to show
                # This prevents squishing when window is partially off-screen

                # Calculate offset from window origin to visible area
                offset_x = visible_window_rect.x() - original_window_rect.x()
                offset_y = visible_window_rect.y() - original_window_rect.y()

                # Create source rectangle (portion of captured image to display)
                source_rect = QRect(
                    offset_x,
                    offset_y,
                    visible_window_rect.width(),
                    visible_window_rect.height(),
                )

                # Ensure source rectangle is within pixmap bounds
                source_rect = source_rect.intersected(window_pixmap.rect())

                if not source_rect.isEmpty():
                    # Draw only the visible portion - no squishing
                    painter.drawPixmap(visible_window_rect, window_pixmap, source_rect)
        # else: Preview OFF - don't draw window content, only border will be drawn below

        # Always draw border for clarity (both modes)
        pen = painter.pen()
        pen.setColor(CaptiXColors.THEME_BLUE)  # Blue border that stands out better
        pen.setWidth(UIConstants.HIGHLIGHT_BORDER_WIDTH)  # 2 pixel width for better visibility over any content
        pen.setStyle(Qt.PenStyle.DashDotLine)  # Dash-dot style to match guidelines
        painter.setPen(pen)
        painter.drawRect(visible_window_rect)

        logger.debug(
            f"Window {'content preview' if self.is_preview_mode_enabled else 'border highlight'} drawn: "
            f"{visible_window_rect.width()}x{visible_window_rect.height()} "
            f"at ({visible_window_rect.x()}, {visible_window_rect.y()}) - {window.title}"
        )

    def draw_crosshair_guidelines(self, painter: QPainter):
        """Draw dash-dot guidelines from cursor to screen edges for precision targeting.

        The actual crosshair cursor is provided by Qt.CursorShape.CrossCursor.
        This method only draws the guideline extensions to screen edges.
        """
        # Only draw guidelines if we have cursor position and overlay is visible
        if self._overlay_opacity <= 0:
            return

        screen_rect = self.rect()
        cursor_x = self.cursor_x
        cursor_y = self.cursor_y

        # Configure pen for dash-dot guidelines
        pen = painter.pen()
        pen.setColor(CaptiXColors.THEME_BLUE)  # Same blue as window highlight
        pen.setWidth(
            UIConstants.HIGHLIGHT_BORDER_WIDTH
        )  # Thicker lines for better visibility (matches window border width)
        pen.setStyle(Qt.PenStyle.DashDotLine)  # Dash-dot style
        painter.setPen(pen)

        # Draw horizontal guideline (left to right across full screen)
        painter.drawLine(screen_rect.left(), cursor_y, screen_rect.right(), cursor_y)

        # Draw vertical guideline (top to bottom across full screen)
        painter.drawLine(cursor_x, screen_rect.top(), cursor_x, screen_rect.bottom())

        logger.debug(
            f"Crosshair guidelines drawn at cursor position ({cursor_x}, {cursor_y})"
        )

    def draw_selection_dimensions(self, painter: QPainter):
        """Draw selection dimensions anchored to bottom-right corner of selection."""
        if not self.selection_rect or self.selection_rect.isEmpty():
            return

        # Get selection dimensions
        width = self.selection_rect.width()
        height = self.selection_rect.height()

        # Format dimensions text
        dimensions_text = f"{width} × {height}"

        # Set up font and calculate text size
        from PyQt6.QtGui import QFont, QFontMetrics

        font = QFont("Arial", 12, QFont.Weight.Bold)  # Smaller font size
        painter.setFont(font)
        font_metrics = QFontMetrics(font)
        text_rect = font_metrics.boundingRect(dimensions_text)

        # Add padding around text
        padding = UIConstants.DIMENSIONS_DISPLAY_PADDING  # Smaller padding
        text_bg_width = text_rect.width() + (padding * 2)
        text_bg_height = text_rect.height() + (padding * 2)

        # Position at bottom-right corner of selection, inside the selection area
        selection_bottom_right_x = self.selection_rect.right()
        selection_bottom_right_y = self.selection_rect.bottom()

        # Anchor to bottom-right, inside selection
        bg_x = selection_bottom_right_x - text_bg_width - UIConstants.DIMENSIONS_DISPLAY_MARGIN  # 10px margin from edge
        bg_y = selection_bottom_right_y - text_bg_height - UIConstants.DIMENSIONS_DISPLAY_MARGIN  # 10px margin from edge

        # Create background rectangle
        bg_rect = QRect(bg_x, bg_y, text_bg_width, text_bg_height)

        # Draw semi-transparent background
        painter.fillRect(bg_rect, CaptiXColors.SEMI_TRANSPARENT_BLACK)  # Dark background

        # Draw the dimensions text (no border)
        text_pen = painter.pen()
        text_pen.setColor(CaptiXColors.WHITE_TEXT)  # White text
        text_pen.setWidth(1)
        painter.setPen(text_pen)

        # Center text within background rectangle
        text_x = bg_x + padding
        text_y = bg_y + padding + font_metrics.ascent()
        painter.drawText(text_x, text_y, dimensions_text)

        logger.debug(
            f"Selection dimensions displayed: {dimensions_text} at ({bg_x}, {bg_y})"
        )

    def _get_window_content_geometry(self, window_info: WindowInfo) -> QRect:
        """
        Calculate the content-only geometry for a window by detecting and excluding borders.

        This provides immediate border detection without waiting for window capture to complete.
        Uses the same border detection logic as capture_window_pure_content.

        Args:
            window_info: WindowInfo object containing window details

        Returns:
            QRect representing the content area (borders excluded)
        """
        try:
            # Get the window object for border detection
            if self.window_detector:
                window_obj = self.window_detector.display.create_resource_object(
                    "window", window_info.window_id
                )

                # Detect border sizes using the same method as capture
                left_border, right_border, top_border, bottom_border = (
                    self.window_detector.get_window_frame_extents(window_obj)
                )

                # Calculate content-only geometry
                content_x = window_info.x + left_border
                content_y = window_info.y + top_border
                content_width = window_info.width - left_border - right_border
                content_height = window_info.height - top_border - bottom_border

                # Ensure positive dimensions
                content_width = max(1, content_width)
                content_height = max(1, content_height)

                logger.debug(
                    f"Window content geometry calculated: borders L={left_border} R={right_border} "
                    f"T={top_border} B={bottom_border}, content {content_width}x{content_height} "
                    f"at ({content_x}, {content_y})"
                )

                return QRect(content_x, content_y, content_width, content_height)

        except Exception as e:
            logger.warning(f"Failed to calculate content geometry, using full window: {e}")

        # Fallback: use full window bounds if border detection fails
        return QRect(window_info.x, window_info.y, window_info.width, window_info.height)

    def showEvent(self, event):
        """Handle window show event."""
        logger.info("[OVERLAY] showEvent triggered - overlay is being displayed")
        show_start = time.perf_counter()

        super().showEvent(event)

        # Ensure window has focus to receive key events
        self.setFocus()
        self.activateWindow()
        self.raise_()

        # Capture full screenshot IMMEDIATELY for instant display
        if not self._captures_complete and not self.frozen_screen:
            logger.info("[OVERLAY] Capturing full screenshot immediately...")
            capture_start = time.perf_counter()
            self.capture_frozen_screen()
            capture_time = time.perf_counter() - capture_start
            logger.info(f"[OVERLAY] Full screenshot captured in {capture_time*1000:.1f}ms")

            # Trigger repaint to show frozen screen right away
            self.update()
            logger.info("[OVERLAY] Starting window captures in background")

        # Start the fade-in animation now that the window is visible
        if self.fade_animation and self.fade_animation.state() != QPropertyAnimation.State.Running:
            self.fade_animation.start()
            logger.info("Fade-in animation started")

        # Capture windows in background thread (after full screenshot is done)
        if not self._captures_complete:
            # Set thread start time for watchdog monitoring
            self.thread_start_time = time.time()
            capture_thread = threading.Thread(target=self._do_window_captures, daemon=True)
            capture_thread.start()
            logger.info("[OVERLAY] Started background window capture thread with watchdog monitoring")

        show_time = time.perf_counter() - show_start
        logger.info(f"[OVERLAY] showEvent completed in {show_time*1000:.1f}ms - overlay ready for interaction")

    def _do_window_captures(self):
        """Perform window captures in background thread (full screenshot already done).

        Thread Safety: This method runs in a background thread during initialization.
        The lock protects all writes to captured_windows and _captures_complete.
        After the lock is released and the signal is emitted, captured_windows
        becomes effectively read-only, so main thread can read without locks.
        """
        try:
            logger.info("[THREAD] Background window capture thread started")
            thread_start = time.perf_counter()

            with self._capture_lock:
                # Full screenshot was already captured in showEvent
                # Now capture individual windows
                capture_start = time.perf_counter()
                self.capture_all_windows()
                capture_time = time.perf_counter() - capture_start
                logger.info(f"[THREAD] Window captures completed in {capture_time*1000:.1f}ms")

                self._captures_complete = True
                # Clear thread start time to stop watchdog monitoring
                self.thread_start_time = None

            # Signal completion (thread-safe)
            # After this signal, main thread can safely read captured_windows without locks
            self.captures_complete.emit()

            total_time = time.perf_counter() - thread_start
            logger.info(f"[THREAD] Background thread completed successfully in {total_time*1000:.1f}ms")
        except Exception as e:
            logger.error(f"Error in background window capture thread: {e}")
            # Clear thread start time even on error
            self.thread_start_time = None

    def _on_captures_complete(self):
        """Handle capture completion in main thread."""
        logger.info("Background captures complete, updating display")
        self.update()  # Force repaint with captured content
        
    def closeEvent(self, event):
        """Handle window close event."""
        logger.info("Overlay window closing")

        # Stop failsafe timers first
        if self.thread_watchdog_timer:
            self.thread_watchdog_timer.stop()
            self.thread_watchdog_timer = None

        if self.heartbeat_timer:
            self.heartbeat_timer.stop()
            self.heartbeat_timer = None

        # Stop external watchdog
        if self.external_watchdog:
            self.external_watchdog.stop_watchdog()
            self.external_watchdog = None

        # Stop and clean up animation
        if self.fade_animation:
            self.fade_animation.stop()
            self.fade_animation = None

        # Clean up capture system
        if self.capture_system:
            self.capture_system.cleanup()
            self.capture_system = None

        # Clean up window detector
        if self.window_detector:
            self.window_detector.cleanup()
            self.window_detector = None

        # Clean up frozen screen pixmap
        self.frozen_screen = None

        # Clean up enhanced capture data
        self.frozen_full_image = None
        with self._capture_lock:
            self.captured_windows.clear()

        # Clean up magnifier widget
        if self.magnifier:
            self.magnifier.hide_magnifier()
            self.magnifier.close()
            self.magnifier = None

        # Clear highlighting state
        self.highlighted_window = None

        # Ensure application exits when window is closed
        app = QApplication.instance()
        if app:
            app.quit()
        super().closeEvent(event)


class ScreenshotUI:
    """Main screenshot UI controller."""
    
    def __init__(self):
        self.app: Optional[QApplication] = None
        self.overlay: Optional[ScreenshotOverlay] = None
        
    def run(self):
        """Launch the screenshot UI."""
        try:
            # Create QApplication if it doesn't exist
            self.app = QApplication.instance()
            if not self.app:
                self.app = QApplication(sys.argv)
                
            logger.info("Starting screenshot UI...")

            # Create and show overlay in fullscreen mode
            self.overlay = ScreenshotOverlay()
            self.overlay.showFullScreen()  # Use true fullscreen instead of show()

            # Run the application
            return self.app.exec()
            
        except Exception as e:
            logger.error(f"Error running screenshot UI: {e}")
            return 1
        finally:
            self.cleanup()
            
    def cleanup(self):
        """Clean up resources."""
        if self.overlay:
            self.overlay.close()
            self.overlay = None
            
        logger.info("Screenshot UI cleanup completed")


def main():
    """Main entry point for screenshot UI."""
    # Check if another instance is already running
    from captix.utils.single_instance import SingleInstanceManager

    instance_manager = SingleInstanceManager()
    if not instance_manager.acquire():
        # Another instance is running - exit silently
        logger.info("Another screenshot UI instance is already running, exiting")
        return 0

    # Keep instance_manager alive for the lifetime of the UI
    ui = ScreenshotUI()
    ui.instance_manager = instance_manager
    return ui.run()