#!/usr/bin/env python3
"""
CaptiX Screenshot UI - Interactive overlay for screenshot selection

Phase 4, Block 4.3: Dark Overlay Layer (Enhanced)
- Add 50% dark semi-transparent overlay with smooth transition
- Animate from 0% to 50% opacity over 0.25 seconds
- Cover entire screen with darkened layer
- Test overlay opacity and visibility
- Ensure overlay doesn't interfere with events

Previous blocks completed:
- Block 4.1: PyQt6 Setup & Basic Overlay
- Block 4.2: Screen Capture & Frozen Background
"""

import sys
import logging
from typing import Optional
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QRect, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QKeyEvent, QPaintEvent, QPainter, QColor, QPixmap
from PIL import Image
from utils.capture import ScreenCapture

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScreenshotOverlay(QWidget):
    """Full-screen transparent overlay for screenshot selection."""
    
    def __init__(self):
        super().__init__()
        self.frozen_screen: Optional[QPixmap] = None
        self.capture_system: Optional[ScreenCapture] = None
        self._overlay_opacity: float = 0.0  # Start with no opacity
        self.fade_animation: Optional[QPropertyAnimation] = None

        self.setup_window()
        self.capture_frozen_screen()
        self.setup_geometry()
        self.setup_animation()
        
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

    def paintEvent(self, event: QPaintEvent):
        """Paint the overlay with frozen screen background and dark overlay."""
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

        # Clean up frozen screen pixmap
        self.frozen_screen = None

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