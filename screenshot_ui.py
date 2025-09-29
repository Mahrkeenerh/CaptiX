#!/usr/bin/env python3
"""
CaptiX Screenshot UI - Interactive overlay for screenshot selection

Phase 4, Block 4.5: Basic Mouse Event Handling
- Detect mouse clicks on overlay
- Distinguish between single clicks and drag starts
- Handle highlighted window click vs desktop click
- Add basic click position logging

Previous blocks completed:
- Block 4.1: PyQt6 Setup & Basic Overlay
- Block 4.2: Screen Capture & Frozen Background
- Block 4.3: Dark Overlay Layer (Enhanced)
- Block 4.4: Window Highlighting System
"""

import sys
import logging
import time
from typing import Optional
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QRect, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QKeyEvent, QPaintEvent, QPainter, QColor, QPixmap, QMouseEvent
from PIL import Image
from utils.capture import ScreenCapture
from utils.window_detect import WindowDetector, WindowInfo

# Set up logging
logging.basicConfig(level=logging.DEBUG)  # Enable debug logging
logger = logging.getLogger(__name__)


class ScreenshotOverlay(QWidget):
    """Full-screen transparent overlay for screenshot selection."""
    
    def __init__(self):
        super().__init__()
        self.frozen_screen: Optional[QPixmap] = None
        self.capture_system: Optional[ScreenCapture] = None
        self.window_detector: Optional[WindowDetector] = None
        self._overlay_opacity: float = 0.0  # Start with no opacity
        self.fade_animation: Optional[QPropertyAnimation] = None

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

        self.setup_window()
        self.capture_frozen_screen()
        self.setup_geometry()
        self.setup_animation()
        self.setup_window_detection()
        
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

        # Set window title for debugging
        self.setWindowTitle("CaptiX Screenshot Overlay")
        
        logger.info("Overlay window configured")

    def capture_frozen_screen(self):
        """Capture the current screen state to use as frozen background."""
        try:
            logger.info("Capturing frozen screen background...")

            # Initialize capture system
            self.capture_system = ScreenCapture()

            # Capture full screen with cursor
            screen_image = self.capture_system.capture_full_screen(include_cursor=True)

            if screen_image:
                # Convert PIL Image to QPixmap
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
                from PyQt6.QtGui import QImage

                qimage = QImage(image_bytes, width, height, QImage.Format.Format_RGB888)
                self.frozen_screen = QPixmap.fromImage(qimage)

                logger.info(f"Frozen screen captured: {width}x{height}")
            else:
                logger.error("Failed to capture screen for frozen background")

        except Exception as e:
            logger.error(f"Error capturing frozen screen: {e}")
            self.frozen_screen = None

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
        """Handle mouse move events for window highlighting."""
        # Convert local coordinates to global screen coordinates
        global_pos = self.mapToGlobal(event.position().toPoint())

        # Update window highlighting based on cursor position
        self.update_window_highlight(global_pos.x(), global_pos.y())

        # Check if this might be the start of a drag operation
        if self.mouse_pressed:
            current_pos = (global_pos.x(), global_pos.y())
            distance_moved = abs(current_pos[0] - self.press_position[0]) + abs(
                current_pos[1] - self.press_position[1]
            )

            if distance_moved >= self.drag_threshold_px:
                logger.info(
                    f"Drag detected: moved {distance_moved}px from press position"
                )
                # TODO: Will be implemented in Block 4.7 (Selection Rectangle Drawing)

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

            logger.info(
                f"Mouse released at {current_pos}, duration: {click_duration_ms:.1f}ms, moved: {distance_moved}px"
            )

            # Determine click type and handle accordingly
            if (
                click_duration_ms <= self.click_threshold_ms
                and distance_moved < self.drag_threshold_px
            ):
                # This is a single click
                self.handle_single_click(self.press_position[0], self.press_position[1])
            else:
                # This was a drag operation
                self.handle_drag_complete(self.press_position, current_pos)

        super().mouseReleaseEvent(event)

    def handle_single_click(self, x: int, y: int):
        """Handle single click - capture window or full screen."""
        logger.info(f"Processing single click at global position ({x}, {y})")

        # Use the window that was highlighted when the click started
        target_window = self.highlighted_window

        if target_window and not target_window.is_root:
            # Clicked on a window - capture that window
            logger.info(
                f"Single click on window: {target_window.title} ({target_window.class_name})"
            )
            logger.info(
                f"  Window geometry: {target_window.width}x{target_window.height} at ({target_window.x}, {target_window.y})"
            )

            # TODO: Block 4.6 will implement actual window capture
            # For now, just log the intended action
            logger.info("Action: Would capture this specific window")

        else:
            # Clicked on desktop or no window detected - capture full screen
            logger.info("Single click on desktop - will capture full screen")

            # TODO: Block 4.6 will implement actual full screen capture
            # For now, just log the intended action
            logger.info("Action: Would capture full screen")

    def handle_drag_complete(self, start_pos: tuple, end_pos: tuple):
        """Handle completed drag operation - capture selected area."""
        x1, y1 = start_pos
        x2, y2 = end_pos

        # Calculate selection rectangle
        left = min(x1, x2)
        top = min(y1, y2)
        right = max(x1, x2)
        bottom = max(y1, y2)

        width = right - left
        height = bottom - top

        logger.info(
            f"Drag completed: selection area {width}x{height} at ({left}, {top})"
        )

        # TODO: Block 4.7+ will implement actual area selection capture
        # For now, just log the intended action
        logger.info(f"Action: Would capture area {left},{top} {width}x{height}")

    def paintEvent(self, event: QPaintEvent):
        """Paint the overlay with frozen screen background, dark overlay, and window highlight."""
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

        # Draw the dark overlay layer with animated opacity
        # Convert opacity from 0.0-1.0 to 0-255 alpha value
        alpha_value = int(self._overlay_opacity * 255)
        dark_overlay_color = QColor(0, 0, 0, alpha_value)
        painter.fillRect(self.rect(), dark_overlay_color)

        if alpha_value > 0:
            logger.debug(
                f"Dark overlay layer drawn ({self._overlay_opacity:.1%} opacity, alpha={alpha_value})"
            )

        # Draw window highlight if we have a highlighted window
        if (
            self.highlighted_window
            and not self.highlighted_window.is_root
            and alpha_value > 0
        ):
            self.draw_window_highlight(painter)

    def draw_window_highlight(self, painter: QPainter):
        """Draw highlight overlay over the currently highlighted window."""
        window = self.highlighted_window
        if not window:
            return

        # Create window rectangle
        window_rect = QRect(window.x, window.y, window.width, window.height)

        # Ensure window rectangle is within screen bounds
        screen_rect = self.rect()
        window_rect = window_rect.intersected(screen_rect)

        if window_rect.isEmpty():
            return

        # Draw light gray-white highlight over the window area
        # Use a light color that's visible over the dark overlay
        highlight_color = QColor(
            200, 200, 200, 60
        )  # Light gray-white with 60/255 alpha (~24%)
        painter.fillRect(window_rect, highlight_color)

        # Draw a subtle border around the highlighted window
        border_color = QColor(
            255, 255, 255, 120
        )  # Brighter white border with more alpha
        painter.setPen(border_color)
        painter.drawRect(window_rect)

        logger.debug(
            f"Window highlight drawn: {window_rect.width()}x{window_rect.height()} "
            f"at ({window_rect.x()}, {window_rect.y()})"
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