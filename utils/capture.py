"""
Core X11 screen capture functionality for CaptiX.

This module handles all screen capture operations including:
- Full screen capture
- Area-based capture
- Multi-monitor support
- Cursor inclusion
- PNG file saving
- Clipboard integration
"""

import os
import ctypes
import ctypes.util
from typing import Tuple, Optional
from datetime import datetime
from pathlib import Path

from Xlib import display, X
from Xlib.ext import randr
from PIL import Image
import logging

# Import clipboard functionality
from .clipboard import copy_image_to_clipboard

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# XFixes cursor capture using ctypes (based on PyXCursor)
PIXEL_DATA_PTR = ctypes.POINTER(ctypes.c_ulong)
Atom = ctypes.c_ulong


class XFixesCursorImage(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_short),
        ("y", ctypes.c_short),
        ("width", ctypes.c_ushort),
        ("height", ctypes.c_ushort),
        ("xhot", ctypes.c_ushort),
        ("yhot", ctypes.c_ushort),
        ("cursor_serial", ctypes.c_ulong),
        ("pixels", PIXEL_DATA_PTR),
        ("atom", Atom),
        ("name", ctypes.c_char_p),
    ]


class Display(ctypes.Structure):
    pass


class XFixesCursor:
    """Direct XFixes cursor access using ctypes."""

    def __init__(self, display_name=None):
        """Initialize XFixes cursor interface."""
        if not display_name:
            try:
                display_name = os.environ["DISPLAY"].encode("utf-8")
            except KeyError:
                raise Exception("$DISPLAY not set.")

        # Load XFixes library
        XFixes = ctypes.util.find_library("Xfixes")
        if not XFixes:
            raise Exception("No XFixes library found.")
        self.XFixeslib = ctypes.cdll.LoadLibrary(XFixes)

        # Load X11 library
        x11 = ctypes.util.find_library("X11")
        if not x11:
            raise Exception("No X11 library found.")
        self.xlib = ctypes.cdll.LoadLibrary(x11)

        # Set up XFixesGetCursorImage function
        XFixesGetCursorImage = self.XFixeslib.XFixesGetCursorImage
        XFixesGetCursorImage.restype = ctypes.POINTER(XFixesCursorImage)
        XFixesGetCursorImage.argtypes = [ctypes.POINTER(Display)]
        self.XFixesGetCursorImage = XFixesGetCursorImage

        # Set up XOpenDisplay function
        XOpenDisplay = self.xlib.XOpenDisplay
        XOpenDisplay.restype = ctypes.POINTER(Display)
        XOpenDisplay.argtypes = [ctypes.c_char_p]

        # Open display
        self.display = XOpenDisplay(display_name)
        if not self.display:
            raise Exception(f"Could not open display {display_name}")

    def get_cursor_image(self):
        """Get cursor image data."""
        cursor_data = self.XFixesGetCursorImage(self.display)
        if cursor_data:
            return cursor_data[0]
        return None

    def close(self):
        """Close the display connection."""
        if hasattr(self, "display") and self.display:
            self.xlib.XCloseDisplay(self.display)


class ScreenCapture:
    """Handles X11 screen capture operations with cursor inclusion."""
    
    def __init__(self):
        """Initialize the screen capture system."""
        self.display = display.Display()
        self.screen = self.display.screen()
        self.root = self.screen.root

        # Initialize XFixes cursor interface
        try:
            self.xfixes_cursor = XFixesCursor()
        except Exception as e:
            logger.warning(f"Failed to initialize XFixes cursor: {e}")
            self.xfixes_cursor = None

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
        Add the actual cursor to the captured image using XFixes extension.

        Args:
            image: The captured image
            offset_x: X offset of the capture area
            offset_y: Y offset of the capture area

        Returns:
            Image with actual cursor overlaid
        """
        try:
            # Check if XFixes cursor is available
            if not self.xfixes_cursor:
                return image

            # Get the actual cursor image using XFixes
            cursor_image = self.xfixes_cursor.get_cursor_image()

            if cursor_image and cursor_image.width > 0 and cursor_image.height > 0:
                # Get cursor position from XFixes data
                cursor_x = cursor_image.x - offset_x
                cursor_y = cursor_image.y - offset_y

                # Check if cursor is within the captured area
                if 0 <= cursor_x < image.width and 0 <= cursor_y < image.height:
                    # Convert cursor data to PIL Image
                    cursor_pil = self._convert_cursor_to_pil(cursor_image)

                    if cursor_pil:
                        # Calculate hotspot position
                        hotspot_x = cursor_x - cursor_image.xhot
                        hotspot_y = cursor_y - cursor_image.yhot

                        # Ensure we don't paste outside image bounds
                        if (
                            hotspot_x + cursor_image.width > 0
                            and hotspot_y + cursor_image.height > 0
                            and hotspot_x < image.width
                            and hotspot_y < image.height
                        ):
                            # Paste cursor onto the main image
                            if cursor_pil.mode == "RGBA":
                                image.paste(
                                    cursor_pil, (hotspot_x, hotspot_y), cursor_pil
                                )
                            else:
                                image.paste(cursor_pil, (hotspot_x, hotspot_y))

                            logger.debug(
                                f"Added native cursor at ({hotspot_x}, {hotspot_y})"
                            )

        except Exception as e:
            logger.error(f"Failed to add native cursor: {e}")

        return image

    def _convert_cursor_to_pil(self, cursor_image) -> Optional[Image.Image]:
        """
        Convert XFixes cursor image to PIL Image.

        Args:
            cursor_image: XFixes cursor image object

        Returns:
            PIL Image or None if conversion failed
        """
        try:
            width = cursor_image.width
            height = cursor_image.height

            # Cursor data is in ARGB format (32-bit) from the pixels pointer
            pixels_ptr = cursor_image.pixels
            if not pixels_ptr:
                return None

            # Convert to RGBA format for PIL
            rgba_data = bytearray(width * height * 4)

            for i in range(width * height):
                # Extract ARGB components from 32-bit value
                argb = pixels_ptr[i]
                a = (argb >> 24) & 0xFF
                r = (argb >> 16) & 0xFF
                g = (argb >> 8) & 0xFF
                b = argb & 0xFF

                # Store as RGBA
                base_idx = i * 4
                rgba_data[base_idx] = r
                rgba_data[base_idx + 1] = g
                rgba_data[base_idx + 2] = b
                rgba_data[base_idx + 3] = a

            return Image.frombytes("RGBA", (width, height), bytes(rgba_data))

        except Exception as e:
            logger.error(f"Failed to convert cursor image: {e}")
            return None

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
            if self.xfixes_cursor:
                self.xfixes_cursor.close()
            self.display.close()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")


def capture_screenshot(
    x: int = None,
    y: int = None,
    width: int = None,
    height: int = None,
    save_path: str = None,
    include_cursor: bool = True,
    copy_to_clipboard: bool = True,
) -> Tuple[str, int]:
    """
    Convenient function to capture a screenshot.

    Args:
        x, y, width, height: Area to capture (None for full screen)
        save_path: Where to save (None for default location)
        include_cursor: Whether to include cursor
        copy_to_clipboard: Whether to copy to clipboard (default: True)

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
        filepath, file_size = capture.save_screenshot(image, save_path)

        # Copy to clipboard if requested
        if copy_to_clipboard:
            try:
                if copy_image_to_clipboard(filepath):
                    logger.info("Screenshot copied to clipboard")
                else:
                    logger.warning("Failed to copy screenshot to clipboard")
            except Exception as e:
                logger.warning(f"Clipboard copy failed: {e}")

        return filepath, file_size
        
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