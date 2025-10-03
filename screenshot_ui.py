#!/usr/bin/env python3
"""
CaptiX Screenshot UI - Interactive overlay for screenshot selection

Phase 4, Block 4.10: Selection Dimensions Display - COMPLETED
- Show selection width x height in dimensions display
- Anchor dimensions to bottom-right corner of selection, inside selection area
- Format: "W × H" with clean styling and readable background

Previous blocks completed:
- Block 4.1: PyQt6 Setup & Basic Overlay
- Block 4.2: Screen Capture & Frozen Background
- Block 4.3: Dark Overlay Layer (Enhanced)
- Block 4.4: Window Highlighting System
- Block 4.5: Basic Mouse Event Handling
- Block 4.6: Enhanced Temporal Consistency Capture System
- Block 4.7: Selection Rectangle Drawing
- Block 4.8: Basic Magnifier Widget
- Block 4.9: Enhanced Magnifier Features
- Block 4.10: Selection Dimensions Display

Next blocks:
- Block 4.11: Capture Integration & Polish
- Block 4.12: Window Background Post-Processing
"""

import sys
import logging
import time
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
from utils.capture import ScreenCapture, list_visible_windows
from utils.clipboard import copy_image_to_clipboard
from utils.window_detect import WindowDetector, WindowInfo
from utils.magnifier import MagnifierWidget

# Set up logging
logging.basicConfig(level=logging.DEBUG)  # Enable debug logging
logger = logging.getLogger(__name__)


@dataclass
class CapturedWindow:
    """Stores a captured window with its metadata at capture time."""

    window_info: WindowInfo
    image: Image.Image  # PIL Image of just this window
    qpixmap: Optional[QPixmap] = None  # Cached QPixmap for efficient rendering
    geometry: QRect = None  # Position/size at capture time

    def __post_init__(self):
        """Initialize geometry from window_info."""
        if self.geometry is None:
            self.geometry = QRect(
                self.window_info.x,
                self.window_info.y,
                self.window_info.width,
                self.window_info.height,
            )


class ScreenshotOverlay(QWidget):
    """Full-screen transparent overlay for screenshot selection."""
    
    def __init__(self):
        super().__init__()
        self.frozen_screen: Optional[QPixmap] = None
        self.capture_system: Optional[ScreenCapture] = None
        self.window_detector: Optional[WindowDetector] = None
        self._overlay_opacity: float = 0.0  # Start with no opacity
        self.fade_animation: Optional[QPropertyAnimation] = None

        # Enhanced capture system (Block 4.6a)
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

        # Mouse click tracking state (Block 4.5)
        self.mouse_pressed: bool = False
        self.press_start_time: float = 0.0
        self.press_position: tuple = (
            0,
            0,
        )  # Global coordinates where mouse was pressed
        self.click_threshold_ms: int = 200  # Max time for click vs drag (milliseconds)
        self.drag_threshold_px: int = 5  # Min pixel movement to start drag

        # Selection rectangle state (Block 4.7)
        self.is_dragging: bool = False
        self.current_drag_pos: tuple = (0, 0)  # Current mouse position during drag
        self.selection_rect: Optional[QRect] = None  # Current selection rectangle

        # Crosshair guideline state (QoL Feature)
        self.last_crosshair_pos: tuple = (-1, -1)  # Track last crosshair position

        # Window preview mode toggle (Right-click feature)
        self.is_preview_mode_enabled: bool = (
            True  # Default to True for bring-to-front preview
        )

        # Magnifier widget state (Block 4.8)
        self.magnifier: Optional[MagnifierWidget] = None

        self.setup_window()
        self.capture_frozen_screen()
        self.setup_geometry()
        self.setup_animation()
        self.setup_window_detection()
        self.setup_magnifier()
        
    def setup_window(self):
        """Configure the overlay window properties."""
        # Make window frameless and always on top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
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
        
        logger.info("Overlay window configured")

    def capture_frozen_screen(self):
        """Capture the current screen state and all individual windows to use as frozen background."""
        try:
            logger.info("Capturing frozen screen background and all windows...")

            # Initialize capture system
            self.capture_system = ScreenCapture()

            # Capture full screen with cursor
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

                # Now capture all individual windows (Block 4.6a enhancement)
                self.capture_all_windows()
            else:
                logger.error("Failed to capture screen for frozen background")

        except Exception as e:
            logger.error(f"Error capturing frozen screen: {e}")
            self.frozen_screen = None
            self.frozen_full_image = None

    def capture_all_windows(self):
        """Capture all visible windows individually for temporal consistency."""
        try:
            logger.info("Capturing all visible windows individually...")

            # Get list of all visible windows
            visible_windows = list_visible_windows()

            captured_count = 0
            skipped_count = 0

            for window_info in visible_windows:
                try:
                    # Skip root windows and very small windows (likely system windows)
                    if window_info.is_root or (
                        window_info.width < 50 and window_info.height < 50
                    ):
                        logger.debug(
                            f"Skipping window: {window_info.title} ({window_info.width}x{window_info.height})"
                        )
                        skipped_count += 1
                        continue

                    # Capture this window's pure content without cursor
                    window_image = self.capture_system.capture_window_pure_content(
                        window_info.window_id, include_cursor=False
                    )

                    if window_image:
                        # Store the captured window
                        captured_window = CapturedWindow(
                            window_info=window_info, image=window_image
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
        """Set up the fade-in animation for the dark overlay."""
        # Create animation for the overlay opacity
        self.fade_animation = QPropertyAnimation(self, b"overlay_opacity")
        self.fade_animation.setDuration(250)  # 0.25 seconds
        self.fade_animation.setStartValue(0.0)  # Start transparent
        self.fade_animation.setEndValue(0.5)  # End at 50% opacity
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        logger.info("Fade animation configured (0.25s, 0% to 50%)")

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
            logger.error(f"Failed to initialize window detection: {e}")
            self.window_detector = None
            self.overlay_window_id = None

    def setup_magnifier(self):
        """Initialize the magnifier widget (Block 4.8)."""
        try:
            self.magnifier = MagnifierWidget()
            logger.info("Magnifier widget initialized (150x150px)")
        except Exception as e:
            logger.error(f"Failed to initialize magnifier widget: {e}")
            self.magnifier = None

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
        if distance_moved < 10:  # Only detect every 10 pixels of movement
            return

        self.last_detection_pos = (x, y)

        try:
            # Get window beneath our overlay using stack walking
            window_info = self.window_detector.get_window_at_position_excluding(
                x, y, exclude_window_id=getattr(self, "overlay_window_id", None)
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
        # Convert local coordinates to global screen coordinates
        global_pos = self.mapToGlobal(event.position().toPoint())

        # Always update cursor position for crosshair guidelines
        self.cursor_x = global_pos.x()
        self.cursor_y = global_pos.y()

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

        # Always update magnifier position during cursor movement (Block 4.8)
        if self.magnifier and self.frozen_screen:
            # Only log occasionally to reduce spam
            if global_pos.x() % 50 == 0:  # Log every 50 pixels
                logger.info(
                    f"Updating magnifier at cursor position ({global_pos.x()}, {global_pos.y()})"
                )
            self.magnifier.set_source_image(self.frozen_screen)
            self.magnifier.update_cursor_position(global_pos.x(), global_pos.y())
            self.magnifier.show_magnifier()
        else:
            if not self.magnifier:
                logger.warning("Magnifier is None!")
            if not self.frozen_screen:
                logger.warning("Frozen screen is None!")

        # Handle active dragging (Block 4.7)
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

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events - start of click or drag."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Convert to global coordinates
            global_pos = self.mapToGlobal(event.position().toPoint())

            # Record press details
            self.mouse_pressed = True
            self.press_start_time = time.time()
            self.press_position = (global_pos.x(), global_pos.y())

            logger.info(f"Mouse pressed at global position: {self.press_position}")

            # Check what's under the cursor at press time
            if self.highlighted_window:
                if self.highlighted_window.is_root:
                    logger.info("Mouse pressed on desktop/root window")
                else:
                    logger.info(
                        f"Mouse pressed on window: {self.highlighted_window.title} ({self.highlighted_window.class_name})"
                    )
            else:
                logger.info("Mouse pressed with no window detected")

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

            # Hide magnifier on mouse release (Block 4.8)
            if self.magnifier:
                self.magnifier.hide_magnifier()

            logger.info(
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
                    logger.info(
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
                        except Exception as e:
                            logger.error(f"Failed to save window capture: {e}")
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
            except Exception as e:
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
                except Exception as e:
                    logger.error(f"Failed to process area capture: {e}")
            else:
                logger.error("No frozen desktop image available for area capture")

            self.close()

        except Exception as e:
            logger.error(f"Error in handle_drag_complete: {e}")
            self.close()

    def paintEvent(self, event: QPaintEvent):
        """Paint the overlay with frozen screen background, dark overlay, selection rectangle, and window highlight."""
        painter = QPainter(self)

        # Draw the frozen screen background if available
        if self.frozen_screen:
            # Draw the frozen screen as background
            painter.drawPixmap(
                self.rect(), self.frozen_screen, self.frozen_screen.rect()
            )
            logger.debug("Frozen screen background drawn")
        else:
            # Fallback: paint a light transparent background
            painter.fillRect(self.rect(), QColor(128, 128, 128, 50))
            logger.warning("No frozen screen available, using fallback background")

        # Draw the dark overlay layer with animated opacity, but not over selection area
        alpha_value = int(self._overlay_opacity * 255)
        dark_overlay_color = QColor(0, 0, 0, alpha_value)

        if self.selection_rect and self.is_dragging:
            # Draw dark overlay everywhere except selection area (Block 4.7)
            screen_rect = self.rect()

            # Create regions for areas outside selection
            # Top area (above selection)
            if self.selection_rect.top() > screen_rect.top():
                top_rect = QRect(
                    screen_rect.left(),
                    screen_rect.top(),
                    screen_rect.width(),
                    self.selection_rect.top() - screen_rect.top(),
                )
                painter.fillRect(top_rect, dark_overlay_color)

            # Bottom area (below selection)
            if self.selection_rect.bottom() < screen_rect.bottom():
                bottom_rect = QRect(
                    screen_rect.left(),
                    self.selection_rect.bottom(),
                    screen_rect.width(),
                    screen_rect.bottom() - self.selection_rect.bottom(),
                )
                painter.fillRect(bottom_rect, dark_overlay_color)

            # Left area (left of selection)
            if self.selection_rect.left() > screen_rect.left():
                left_rect = QRect(
                    screen_rect.left(),
                    max(screen_rect.top(), self.selection_rect.top()),
                    self.selection_rect.left() - screen_rect.left(),
                    min(screen_rect.bottom(), self.selection_rect.bottom())
                    - max(screen_rect.top(), self.selection_rect.top()),
                )
                painter.fillRect(left_rect, dark_overlay_color)

            # Right area (right of selection)
            if self.selection_rect.right() < screen_rect.right():
                right_rect = QRect(
                    self.selection_rect.right(),
                    max(screen_rect.top(), self.selection_rect.top()),
                    screen_rect.right() - self.selection_rect.right(),
                    min(screen_rect.bottom(), self.selection_rect.bottom())
                    - max(screen_rect.top(), self.selection_rect.top()),
                )
                painter.fillRect(right_rect, dark_overlay_color)

            # Draw selection border based on drag direction from origin point
            pen = painter.pen()
            pen.setColor(QColor(0, 150, 255, 200))  # Same blue as window highlight
            pen.setWidth(2)  # 2px border
            pen.setStyle(Qt.PenStyle.DashDotLine)  # Dash-dot style to match guidelines
            painter.setPen(pen)

            # Get selection rectangle bounds
            left = self.selection_rect.left()
            right = self.selection_rect.right()
            top = self.selection_rect.top()
            bottom = self.selection_rect.bottom()

            # Get drag origin and current cursor position
            origin_x, origin_y = self.press_position
            cursor_x, cursor_y = self.cursor_x, self.cursor_y

            # Determine drag direction and draw only relevant borders
            # Draw bottom border if dragging upward (cursor above origin)
            if cursor_y < origin_y:
                painter.drawLine(left, bottom, right, bottom)

            # Draw top border if dragging downward (cursor below origin)
            if cursor_y > origin_y:
                painter.drawLine(left, top, right, top)

            # Draw right border if dragging leftward (cursor left of origin)
            if cursor_x < origin_x:
                painter.drawLine(right, top, right, bottom)

            # Draw left border if dragging rightward (cursor right of origin)
            if cursor_x > origin_x:
                painter.drawLine(left, top, left, bottom)

            # Draw selection dimensions display (Phase 4.10)
            self.draw_selection_dimensions(painter)

            logger.debug(
                f"Selection rectangle drawn: {self.selection_rect.width()}x{self.selection_rect.height()} "
                f"at ({self.selection_rect.x()}, {self.selection_rect.y()})"
            )
        else:
            # No selection - draw dark overlay over entire screen
            painter.fillRect(self.rect(), dark_overlay_color)

        if alpha_value > 0:
            logger.debug(
                f"Dark overlay layer drawn ({self._overlay_opacity:.1%} opacity, alpha={alpha_value})"
            )

        # Draw window highlight if we have a highlighted window (only when not dragging)
        if (
            self.highlighted_window
            and not self.highlighted_window.is_root
            and alpha_value > 0
            and not self.is_dragging
        ):
            self.draw_window_highlight(painter)

        # Draw crosshair guidelines for cursor precision (QoL Feature)
        self.draw_crosshair_guidelines(painter)

    def draw_window_highlight(self, painter: QPainter):
        """Draw highlight overlay over the currently highlighted window - Block 4.6b Enhanced."""
        window = self.highlighted_window
        if not window:
            return

        # Create original window rectangle (full window bounds)
        original_window_rect = QRect(window.x, window.y, window.width, window.height)

        # Calculate visible portion within screen bounds
        screen_rect = self.rect()
        visible_window_rect = original_window_rect.intersected(screen_rect)

        if visible_window_rect.isEmpty():
            return

        # Conditional rendering based on preview mode
        if self.is_preview_mode_enabled:
            # Preview ON: Show full window content (bring-to-front effect)
            # Block 4.6b: Try to show actual captured window content instead of gray overlay
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

                # Debug for terminal window
                if (
                    "terminal" in window.class_name.lower()
                    or "gnome-terminal" in window.class_name.lower()
                ):
                    logger.info(f"Terminal window debug: {window.title}")
                    logger.info(f"  Window size: {window.width}x{window.height}")
                    logger.info(
                        f"  Pixmap size: {window_pixmap.width()}x{window_pixmap.height()}"
                    )
                    logger.info(
                        f"  Visible rect: {visible_window_rect.width()}x{visible_window_rect.height()}"
                    )
                    logger.info(
                        f"  Source rect: {source_rect.width()}x{source_rect.height()}"
                    )
                    # Check if we have the original image mode info
                    if window.window_id in self.captured_windows:
                        original_mode = self.captured_windows[
                            window.window_id
                        ].image.mode
                        logger.info(f"  Original image mode: {original_mode}")
                        logger.info(
                            f"  Image size: {self.captured_windows[window.window_id].image.size}"
                        )
                    else:
                        logger.info("  No captured window data found")
        # else: Preview OFF - don't draw window content, only border will be drawn below

        # Always draw border for clarity (both modes)
        pen = painter.pen()
        pen.setColor(QColor(0, 150, 255, 200))  # Blue border that stands out better
        pen.setWidth(2)  # 2 pixel width for better visibility over any content
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
        pen.setColor(QColor(0, 150, 255, 200))  # Same blue as window highlight
        pen.setWidth(
            2
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
        """Draw selection dimensions anchored to bottom-right corner of selection (Phase 4.10)."""
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
        padding = 6  # Smaller padding
        text_bg_width = text_rect.width() + (padding * 2)
        text_bg_height = text_rect.height() + (padding * 2)

        # Position at bottom-right corner of selection, inside the selection area
        selection_bottom_right_x = self.selection_rect.right()
        selection_bottom_right_y = self.selection_rect.bottom()

        # Anchor to bottom-right, inside selection
        bg_x = selection_bottom_right_x - text_bg_width - 10  # 10px margin from edge
        bg_y = selection_bottom_right_y - text_bg_height - 10  # 10px margin from edge

        # Create background rectangle
        bg_rect = QRect(bg_x, bg_y, text_bg_width, text_bg_height)

        # Draw semi-transparent background
        painter.fillRect(bg_rect, QColor(0, 0, 0, 120))  # Dark background

        # Draw the dimensions text (no border)
        text_pen = painter.pen()
        text_pen.setColor(QColor(255, 255, 255, 255))  # White text
        text_pen.setWidth(1)
        painter.setPen(text_pen)

        # Center text within background rectangle
        text_x = bg_x + padding
        text_y = bg_y + padding + font_metrics.ascent()
        painter.drawText(text_x, text_y, dimensions_text)

        logger.debug(
            f"Selection dimensions displayed: {dimensions_text} at ({bg_x}, {bg_y})"
        )

    def showEvent(self, event):
        """Handle window show event."""
        super().showEvent(event)

        # Ensure window has focus to receive key events
        self.setFocus()
        self.activateWindow()
        self.raise_()

        # Start the fade-in animation
        if self.fade_animation:
            self.fade_animation.start()
            logger.info("Fade-in animation started")

        logger.info("Overlay window shown and focused")
        
    def closeEvent(self, event):
        """Handle window close event."""
        logger.info("Overlay window closing")

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

        # Clean up enhanced capture data (Block 4.6a)
        self.frozen_full_image = None
        self.captured_windows.clear()

        # Clean up magnifier widget (Block 4.8)
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
    ui = ScreenshotUI()
    return ui.run()


if __name__ == "__main__":
    sys.exit(main())