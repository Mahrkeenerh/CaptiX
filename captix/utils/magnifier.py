#!/usr/bin/env python3
"""
CaptiX Magnifier Widget

Features implemented:
- Separate magnifier window (210x210px)
- Position magnifier near cursor
- Capture and display magnified area under cursor
- Follow cursor movement during selection
- 10x zoom magnification
- Pixel grid overlay
- Current cursor coordinates (X, Y)
- Selection dimensions display
"""

import logging
from typing import Optional
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen

logger = logging.getLogger(__name__)


class MagnifierWidget(QWidget):
    """Magnifier widget that shows a zoomed view of the area around the cursor."""

    # Constants for magnifier appearance
    MAGNIFIER_SIZE = 210  # Size for 21 pixels: 21x10 = 210px
    MAGNIFIER_OFFSET = 30  # Offset from cursor when positioned
    ZOOM_FACTOR = 10  # Zoom level (10x)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_window()
        self.source_image: Optional[QPixmap] = None
        self.cursor_x: int = 0
        self.cursor_y: int = 0
        self.is_visible: bool = False
        
    def setup_window(self):
        """Configure the magnifier window properties."""
        # Make window frameless and always on top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.X11BypassWindowManagerHint
        )
        
        # Set fixed size
        self.setFixedSize(self.MAGNIFIER_SIZE, self.MAGNIFIER_SIZE)

        # Set background with refined appearance
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(40, 40, 40, 240); 
                border: 2px solid rgba(255, 255, 255, 180);
                border-radius: 8px;
            }
        """)
        
        # CRITICAL: Never accept focus and never steal keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_X11DoNotAcceptFocus, True)
        
        # Also ensure no mouse events are processed by this widget
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        
        # Initially hidden
        self.hide()
        
    def set_source_image(self, image: QPixmap):
        """Set the source image to magnify from."""
        self.source_image = image
        self.update()
        
    def update_cursor_position(self, x: int, y: int):
        """Update the cursor position and refresh magnifier."""
        self.cursor_x = x
        self.cursor_y = y
        self.position_magnifier()
        self.update()
        
    def position_magnifier(self):
        """Position the magnifier widget at bottom-left of cursor."""
        if not self.source_image:
            return

        # Position at bottom-left of cursor with offset
        magnifier_x = self.cursor_x - self.MAGNIFIER_SIZE - self.MAGNIFIER_OFFSET
        magnifier_y = self.cursor_y + self.MAGNIFIER_OFFSET
        
        # Get screen geometry to ensure we stay within bounds
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().geometry()
        except Exception:
            # Fallback to a reasonable screen size
            from PyQt6.QtCore import QRect
            screen = QRect(0, 0, 1920, 1080)
        
        # Adjust if magnifier would go off-screen (move to other sides of cursor)
        if magnifier_x < 0:
            # Move to right side of cursor if left side is off-screen
            magnifier_x = self.cursor_x + self.MAGNIFIER_OFFSET

        if magnifier_y + self.MAGNIFIER_SIZE > screen.bottom():
            # Move above cursor if bottom side is off-screen
            magnifier_y = self.cursor_y - self.MAGNIFIER_SIZE - self.MAGNIFIER_OFFSET
            
        # Final bounds check
        magnifier_x = max(0, min(magnifier_x, screen.right() - self.MAGNIFIER_SIZE))
        magnifier_y = max(0, min(magnifier_y, screen.bottom() - self.MAGNIFIER_SIZE))
        
        # Move the magnifier window
        self.move(magnifier_x, magnifier_y)
        
    def show_magnifier(self):
        """Show the magnifier widget."""
        if not self.is_visible:
            self.is_visible = True
            self.show()
            self.raise_()  # Bring to front but don't activate
            logger.info(f"Magnifier widget shown at position ({self.x()}, {self.y()})")
        else:
            # Ensure it stays visible and on top (but don't steal focus)
            self.raise_()
            
    def hide_magnifier(self):
        """Hide the magnifier widget."""
        if self.is_visible:
            self.is_visible = False
            self.hide()
            logger.info("Magnifier widget hidden")
        else:
            logger.info("Magnifier already hidden")
            
    def paintEvent(self, event):
        """Paint the magnified view with pixel highlighting and crosshairs."""
        if not self.source_image:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # Keep pixels sharp
        
        # Calculate the area to magnify (centered on cursor)
        magnify_size = self.MAGNIFIER_SIZE // self.ZOOM_FACTOR  # 210/10 = 21px source area
        half_size = magnify_size // 2
        
        # Source rectangle centered on cursor
        source_rect = QRect(
            self.cursor_x - half_size,
            self.cursor_y - half_size,
            magnify_size,
            magnify_size
        )
        
        # Ensure source rectangle is within image bounds
        image_rect = self.source_image.rect()
        source_rect = source_rect.intersected(image_rect)
        
        if source_rect.isEmpty():
            return
            
        # Target rectangle (entire magnifier window)
        target_rect = QRect(0, 0, self.MAGNIFIER_SIZE, self.MAGNIFIER_SIZE)
        
        # Draw the magnified image (no antialiasing for sharp pixels)
        painter.drawPixmap(target_rect, self.source_image, source_rect)
        
        # Calculate pixel size in the magnified view
        pixel_size = self.ZOOM_FACTOR  # Each source pixel becomes 10x10 in display
        
        # Draw pixel grid overlay (subtle)
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))  # Very subtle white grid
        for x in range(0, self.MAGNIFIER_SIZE, pixel_size):
            painter.drawLine(x, 0, x, self.MAGNIFIER_SIZE)
        for y in range(0, self.MAGNIFIER_SIZE, pixel_size):
            painter.drawLine(0, y, self.MAGNIFIER_SIZE, y)
        
        # Highlight the center pixel (current cursor position) with crosshairs
        center_x = self.MAGNIFIER_SIZE // 2
        center_y = self.MAGNIFIER_SIZE // 2
        
        # Find the pixel boundaries that contain the center
        pixel_left = (center_x // pixel_size) * pixel_size
        pixel_top = (center_y // pixel_size) * pixel_size
        
        # Draw highlighted center pixel with solid blue border (pixel-perfect alignment)
        highlight_pen = QPen(QColor(0, 150, 255, 255), 2)  # Solid blue, no dashed style
        painter.setPen(highlight_pen)
        # Draw with pixel-perfect alignment - one pixel larger to right and bottom
        painter.drawRect(pixel_left, pixel_top, pixel_size + 1, pixel_size + 1)
        
        # Draw white crosshair guides extending across entire magnifier (full column/row coverage)
        guide_pen = QPen(QColor(255, 255, 255, 50), pixel_size + 1)  # White with moderate alpha, pixel_size - 1 thick
        painter.setPen(guide_pen)
        
        # Vertical crosshair line covering full column (pixel_size - 1 thick)
        center_pixel_x = pixel_left + pixel_size // 2
        painter.drawLine(center_pixel_x, 0, center_pixel_x, self.MAGNIFIER_SIZE)
        
        # Horizontal crosshair line covering full row (pixel_size - 1 thick)
        center_pixel_y = pixel_top + pixel_size // 2
        painter.drawLine(0, center_pixel_y, self.MAGNIFIER_SIZE, center_pixel_y)
        
        # Draw outer border around the magnifier with dashed style
        border_pen = QPen(QColor(0, 150, 255, 200), 2)  # Same blue as UI theme
        border_pen.setStyle(Qt.PenStyle.DashDotLine)  # Dashed border
        painter.setPen(border_pen)
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

        # Display current cursor coordinates
        from PyQt6.QtGui import QFont
        painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1))  # White text with high opacity
        
        # Draw text background for better readability
        coord_text = f"X: {self.cursor_x}  Y: {self.cursor_y}"
        text_rect = painter.boundingRect(0, 0, 0, 0, Qt.AlignmentFlag.AlignLeft, coord_text)
        text_bg_rect = text_rect.adjusted(-5, -2, 5, 2)
        # Center horizontally, position at top with margin
        center_x = (self.MAGNIFIER_SIZE - text_bg_rect.width()) // 2
        text_bg_rect.moveTopLeft(QPoint(center_x, 8))
        
        # Semi-transparent background for text
        painter.fillRect(text_bg_rect, QColor(0, 0, 0, 120))
        
        # Draw the coordinates text
        painter.drawText(text_bg_rect.adjusted(5, 2, -5, -2), Qt.AlignmentFlag.AlignLeft, coord_text)
        
        painter.end()