#!/usr/bin/env python3
"""
CaptiX Screenshot UI - Interactive overlay for screenshot selection

Phase 4, Block 4.1: PyQt6 Setup & Basic Overlay
- Create basic full-screen transparent window
- Test window appears and covers all monitors
- Add escape key to close window
"""

import sys
import logging
from typing import Optional
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QKeyEvent, QPaintEvent, QPainter, QColor, QPixmap

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScreenshotOverlay(QWidget):
    """Full-screen transparent overlay for screenshot selection."""
    
    def __init__(self):
        super().__init__()
        self.setup_window()
        self.setup_geometry()
        
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
        
    def setup_geometry(self):
        """Set window geometry to cover all screens."""
        app = QApplication.instance()
        if not app:
            logger.error("No QApplication instance found")
            return
            
        # Get all screens
        screens = app.screens()
        if not screens:
            logger.error("No screens found")
            return
            
        # Calculate combined geometry of all screens
        combined_rect = QRect()
        for screen in screens:
            screen_geometry = screen.geometry()
            logger.info(f"Screen found: {screen_geometry.width()}x{screen_geometry.height()} at ({screen_geometry.x()}, {screen_geometry.y()})")
            combined_rect = combined_rect.united(screen_geometry)
            
        # Set window to cover all screens
        self.setGeometry(combined_rect)
        logger.info(f"Overlay geometry set to: {combined_rect.width()}x{combined_rect.height()} at ({combined_rect.x()}, {combined_rect.y()})")
        
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
        """Paint the overlay - currently just transparent."""
        painter = QPainter(self)
        
        # For now, just paint a very transparent background to verify the window is working
        painter.fillRect(self.rect(), QColor(0, 0, 0, 10))  # Very light transparent overlay
        
    def showEvent(self, event):
        """Handle window show event."""
        super().showEvent(event)
        
        # Ensure window has focus to receive key events
        self.setFocus()
        self.activateWindow()
        self.raise_()
        
        logger.info("Overlay window shown and focused")
        
    def closeEvent(self, event):
        """Handle window close event."""
        logger.info("Overlay window closing")
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
            
            # Create and show overlay
            self.overlay = ScreenshotOverlay()
            self.overlay.show()
            
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