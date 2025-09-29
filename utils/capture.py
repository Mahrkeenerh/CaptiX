"""
Core X11 screen capture functionality for CaptiX.

This module handles all screen capture operations including:
- Full screen capture
- Area-based capture 
- Multi-monitor support
- Cursor inclusion
- PNG file saving
"""

import os
from typing import Tuple, Optional
from datetime import datetime
from pathlib import Path

from Xlib import display, X
from Xlib.ext import randr
from PIL import Image
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScreenCapture:
    """Handles X11 screen capture operations with cursor inclusion."""
    
    def __init__(self):
        """Initialize the screen capture system."""
        self.display = display.Display()
        self.screen = self.display.screen()
        self.root = self.screen.root
        
    def get_screen_geometry(self) -> Tuple[int, int, int, int]:
        """
        Get the full screen geometry including all monitors.
        
        Returns:
            Tuple of (x, y, width, height) covering all screens
        """
        try:
            # Try to use RandR extension for multi-monitor support
            screen_resources = randr.get_screen_resources(self.root)
            
            min_x = min_y = 0
            max_x = max_y = 0
            
            for output in screen_resources.outputs:
                output_info = randr.get_output_info(self.root, output, screen_resources.config_timestamp)
                if output_info.connection == randr.Connected and output_info.crtc:
                    crtc_info = randr.get_crtc_info(self.root, output_info.crtc, screen_resources.config_timestamp)
                    
                    min_x = min(min_x, crtc_info.x)
                    min_y = min(min_y, crtc_info.y)
                    max_x = max(max_x, crtc_info.x + crtc_info.width)
                    max_y = max(max_y, crtc_info.y + crtc_info.height)
            
            if max_x > 0 and max_y > 0:
                return (min_x, min_y, max_x - min_x, max_y - min_y)
        
        except Exception as e:
            logger.warning(f"RandR extension failed, falling back to root window geometry: {e}")
        
        # Fallback to root window geometry
        geometry = self.root.get_geometry()
        return (0, 0, geometry.width, geometry.height)
    
    def capture_screen_area(self, x: int, y: int, width: int, height: int, include_cursor: bool = True) -> Optional[Image.Image]:
        """
        Capture a specific area of the screen.
        
        Args:
            x: X coordinate of the top-left corner
            y: Y coordinate of the top-left corner  
            width: Width of the area to capture
            height: Height of the area to capture
            include_cursor: Whether to include the cursor in the capture
            
        Returns:
            PIL Image object or None if capture failed
        """
        try:
            # Get the raw image data from X11
            raw_image = self.root.get_image(x, y, width, height, X.ZPixmap, 0xffffffff)
            
            # Convert to PIL Image
            if raw_image.depth == 24:
                # 24-bit color
                pil_image = Image.frombytes("RGB", (width, height), raw_image.data, "raw", "BGRX")
            elif raw_image.depth == 32:
                # 32-bit color with alpha
                pil_image = Image.frombytes("RGBA", (width, height), raw_image.data, "raw", "BGRA")
            else:
                logger.error(f"Unsupported color depth: {raw_image.depth}")
                return None
            
            # Include cursor if requested
            if include_cursor:
                pil_image = self._add_cursor_to_image(pil_image, x, y)
            
            return pil_image
            
        except Exception as e:
            logger.error(f"Failed to capture screen area: {e}")
            return None
    
    def _add_cursor_to_image(self, image: Image.Image, offset_x: int, offset_y: int) -> Image.Image:
        """
        Add cursor to the captured image.
        
        Args:
            image: The captured image
            offset_x: X offset of the capture area
            offset_y: Y offset of the capture area
            
        Returns:
            Image with cursor overlaid
        """
        try:
            # Query cursor position
            cursor_data = self.root.query_pointer()
            cursor_x = cursor_data.root_x - offset_x
            cursor_y = cursor_data.root_y - offset_y
            
            # Check if cursor is within the captured area
            if 0 <= cursor_x < image.width and 0 <= cursor_y < image.height:
                # For now, we'll draw a simple cursor representation
                # In a more advanced implementation, we could get the actual cursor image
                from PIL import ImageDraw
                
                draw = ImageDraw.Draw(image)
                cursor_size = 16
                
                # Draw a simple arrow cursor
                draw.polygon([
                    (cursor_x, cursor_y),
                    (cursor_x, cursor_y + cursor_size),
                    (cursor_x + 4, cursor_y + cursor_size - 4),
                    (cursor_x + 8, cursor_y + cursor_size + 2),
                    (cursor_x + 10, cursor_y + cursor_size - 1),
                    (cursor_x + 6, cursor_y + cursor_size - 5),
                    (cursor_x + 12, cursor_y + 4)
                ], fill='black', outline='white')
                
        except Exception as e:
            logger.warning(f"Failed to add cursor to image: {e}")
        
        return image
    
    def capture_full_screen(self, include_cursor: bool = True) -> Optional[Image.Image]:
        """
        Capture the full screen including all monitors.
        
        Args:
            include_cursor: Whether to include the cursor in the capture
            
        Returns:
            PIL Image object or None if capture failed
        """
        x, y, width, height = self.get_screen_geometry()
        return self.capture_screen_area(x, y, width, height, include_cursor)
    
    def save_screenshot(self, image: Image.Image, directory: str = None, filename: str = None) -> Tuple[str, int]:
        """
        Save screenshot to file with timestamp naming.
        
        Args:
            image: PIL Image to save
            directory: Directory to save to (defaults to ~/Pictures/Screenshots)
            filename: Custom filename (defaults to timestamp format)
            
        Returns:
            Tuple of (filepath, file_size_bytes)
        """
        # Set default directory
        if directory is None:
            directory = os.path.expanduser("~/Pictures/Screenshots")
        
        # Create directory if it doesn't exist
        Path(directory).mkdir(parents=True, exist_ok=True)
        
        # Generate filename if not provided
        if filename is None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"Screenshot_{timestamp}.png"
        
        # Ensure .png extension
        if not filename.lower().endswith('.png'):
            filename += '.png'
        
        filepath = os.path.join(directory, filename)
        
        try:
            # Save as PNG
            image.save(filepath, "PNG", optimize=True)
            
            # Get actual file size
            file_size = os.path.getsize(filepath)
            
            logger.info(f"Screenshot saved: {filepath} ({file_size} bytes)")
            return filepath, file_size
            
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")
            raise
    
    def cleanup(self):
        """Clean up X11 resources."""
        try:
            self.display.close()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")


def capture_screenshot(x: int = None, y: int = None, width: int = None, height: int = None, 
                      save_path: str = None, include_cursor: bool = True) -> Tuple[str, int]:
    """
    Convenient function to capture a screenshot.
    
    Args:
        x, y, width, height: Area to capture (None for full screen)
        save_path: Where to save (None for default location)
        include_cursor: Whether to include cursor
        
    Returns:
        Tuple of (filepath, file_size_bytes)
    """
    capture = ScreenCapture()
    
    try:
        if x is not None and y is not None and width is not None and height is not None:
            # Capture specific area
            image = capture.capture_screen_area(x, y, width, height, include_cursor)
        else:
            # Capture full screen
            image = capture.capture_full_screen(include_cursor)
        
        if image is None:
            raise RuntimeError("Failed to capture screen")
        
        # Save the screenshot
        return capture.save_screenshot(image, save_path)
        
    finally:
        capture.cleanup()


if __name__ == "__main__":
    # Test the capture functionality
    print("Testing screen capture...")
    try:
        filepath, size = capture_screenshot()
        print(f"Screenshot saved: {filepath}")
        print(f"File size: {size} bytes ({size/1024:.1f} KB)")
    except Exception as e:
        print(f"Error: {e}")