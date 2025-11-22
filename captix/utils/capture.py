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
import threading
from typing import Tuple, Optional, List
from datetime import datetime
from pathlib import Path

from Xlib import display, X
from Xlib.ext import randr
from PIL import Image
import logging

# Import clipboard functionality
from .clipboard import copy_image_to_clipboard
# Import window detection functionality
from .window_detect import WindowDetector, WindowInfo
# Import notification functionality
from .notifications import notify_screenshot_saved
# Import path utilities
from .paths import CaptiXPaths

# Set up logging
logger = logging.getLogger(__name__)

# XFixes cursor capture using ctypes (based on PyXCursor)
PIXEL_DATA_PTR = ctypes.POINTER(ctypes.c_ulong)
Atom = ctypes.c_ulong

# XComposite structures and types
Window = ctypes.c_ulong
Pixmap = ctypes.c_ulong


class XComposite:
    """XComposite extension interface for pure window content capture."""

    def __init__(self, display_name=None):
        """Initialize XComposite interface."""
        if not display_name:
            try:
                display_name = os.environ["DISPLAY"].encode("utf-8")
            except KeyError:
                raise Exception("$DISPLAY not set.")

        # Load XComposite library
        xcomposite_lib = ctypes.util.find_library("Xcomposite")
        if not xcomposite_lib:
            raise Exception("No XComposite library found.")
        self.xcomposite = ctypes.cdll.LoadLibrary(xcomposite_lib)

        # Load X11 library
        x11 = ctypes.util.find_library("X11")
        if not x11:
            raise Exception("No X11 library found.")
        self.xlib = ctypes.cdll.LoadLibrary(x11)

        # Set up XComposite functions
        self.xcomposite.XCompositeQueryExtension.restype = ctypes.c_bool
        self.xcomposite.XCompositeQueryExtension.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]

        self.xcomposite.XCompositeRedirectWindow.restype = None
        self.xcomposite.XCompositeRedirectWindow.argtypes = [
            ctypes.c_void_p,
            Window,
            ctypes.c_int,
        ]

        self.xcomposite.XCompositeUnredirectWindow.restype = None
        self.xcomposite.XCompositeUnredirectWindow.argtypes = [
            ctypes.c_void_p,
            Window,
            ctypes.c_int,
        ]

        self.xcomposite.XCompositeNameWindowPixmap.restype = Pixmap
        self.xcomposite.XCompositeNameWindowPixmap.argtypes = [ctypes.c_void_p, Window]

        # Set up X11 functions
        self.xlib.XOpenDisplay.restype = ctypes.c_void_p
        self.xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]

        self.xlib.XCloseDisplay.restype = None
        self.xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]

        self.xlib.XGetImage.restype = ctypes.c_void_p
        self.xlib.XGetImage.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_ulong,
            ctypes.c_int,
        ]

        self.xlib.XFreePixmap.restype = None
        self.xlib.XFreePixmap.argtypes = [ctypes.c_void_p, Pixmap]

        # Open display
        self.display = self.xlib.XOpenDisplay(display_name)
        if not self.display:
            raise Exception(f"Could not open display {display_name}")

        # Check if XComposite extension is available
        event_base = ctypes.c_int()
        error_base = ctypes.c_int()
        if not self.xcomposite.XCompositeQueryExtension(
            self.display, ctypes.byref(event_base), ctypes.byref(error_base)
        ):
            raise Exception("XComposite extension not available")

    def get_window_pixmap(self, window_id: int) -> Optional[Pixmap]:
        """Get the off-screen pixmap for a window."""
        try:
            # Redirect window to off-screen buffer (CompositeRedirectAutomatic = 1)
            self.xcomposite.XCompositeRedirectWindow(self.display, window_id, 1)

            # Get the window's pixmap
            pixmap = self.xcomposite.XCompositeNameWindowPixmap(self.display, window_id)

            return pixmap if pixmap else None
        except Exception as e:
            # X11 operations can fail with BadWindow, BadMatch, XError, RuntimeError, OSError, etc.
            # depending on window state and X11 library layer. Broad handling is intentional.
            logger.error(f"Failed to get window pixmap: {e}")
            return None

    def redirect_window(self, window_id: int):
        """Redirect window to off-screen buffer for video capture.

        Args:
            window_id: X11 window ID to redirect
        """
        try:
            # CompositeRedirectAutomatic = 1
            self.xcomposite.XCompositeRedirectWindow(self.display, window_id, 1)
            logger.debug(f"Redirected window {window_id} to off-screen buffer")
        except Exception as e:
            logger.error(f"Failed to redirect window: {e}")
            raise

    def unredirect_window(self, window_id: int):
        """Stop redirecting window to off-screen buffer."""
        try:
            self.xcomposite.XCompositeUnredirectWindow(self.display, window_id, 1)
        except Exception as e:
            logger.warning(f"Failed to unredirect window: {e}")

    def capture_frame_raw(self, window_id: int, width: int, height: int) -> Optional[bytes]:
        """Capture raw frame data from XComposite window pixmap for video encoding.

        Args:
            window_id: X11 window ID
            width: Frame width (should be even)
            height: Frame height (should be even)

        Returns:
            Raw BGR24 frame data as bytes, or None on error
        """
        try:
            # Get window pixmap (off-screen buffer)
            pixmap = self.xcomposite.XCompositeNameWindowPixmap(self.display, window_id)
            if not pixmap:
                logger.warning(f"Failed to get pixmap for window {window_id}")
                return None

            # Capture image from pixmap using XGetImage
            # ZPixmap = 2, AllPlanes = 0xFFFFFFFF
            ximage = self.xlib.XGetImage(
                self.display,
                pixmap,
                0, 0,  # x, y offset
                width, height,
                0xFFFFFFFF,  # AllPlanes
                2  # ZPixmap
            )

            if not ximage:
                logger.warning("XGetImage returned NULL")
                return None

            # XImage structure (simplified)
            # We need to read the data pointer from the XImage structure
            # Offset 96 bytes into XImage structure is the data pointer (x86_64)
            data_ptr = ctypes.cast(ximage + 96, ctypes.POINTER(ctypes.c_void_p)).contents

            # Calculate frame size (BGR24 = 3 bytes per pixel)
            frame_size = width * height * 3

            # Read raw pixel data
            # XGetImage returns data in server's byte order (typically BGRX or BGRA)
            # We need BGR24 for FFmpeg, so we need to convert

            # For now, assume 32-bit depth (BGRA) and strip alpha channel
            # This is a simplified version - production code should handle different depths
            raw_data = ctypes.cast(data_ptr, ctypes.POINTER(ctypes.c_ubyte * (width * height * 4)))
            bgra_data = raw_data.contents

            # Convert BGRA to BGR24
            bgr24_data = bytearray(frame_size)
            for i in range(width * height):
                bgr24_data[i * 3] = bgra_data[i * 4]      # B
                bgr24_data[i * 3 + 1] = bgra_data[i * 4 + 1]  # G
                bgr24_data[i * 3 + 2] = bgra_data[i * 4 + 2]  # R

            # Free pixmap (important!)
            self.xlib.XFreePixmap(self.display, pixmap)

            return bytes(bgr24_data)

        except Exception as e:
            logger.error(f"Failed to capture frame: {e}")
            return None

    def close(self):
        if hasattr(self, "display") and self.display:
            self.xlib.XCloseDisplay(self.display)


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
    """Handles X11 screen capture operations with cursor inclusion and pure window capture."""
    
    def __init__(self):
        """Initialize the screen capture system."""
        self.display = display.Display()
        self.screen = self.display.screen()
        self.root = self.screen.root

        # Initialize XFixes cursor interface
        try:
            self.xfixes_cursor = XFixesCursor()
        except Exception as e:
            # X11 extension initialization can fail for various reasons (not installed,
            # permission denied, library mismatch). Graceful degradation is required.
            logger.warning(f"Failed to initialize XFixes cursor: {e}")
            self.xfixes_cursor = None

        # Initialize XComposite interface for pure window capture
        try:
            self.xcomposite = XComposite()
        except Exception as e:
            # XComposite extension may not be available on all systems.
            # Screenshot functionality continues without window-specific features.
            logger.warning(f"Failed to initialize XComposite: {e}")
            self.xcomposite = None

        # Initialize window detector for window-based capture
        try:
            self.window_detector = WindowDetector()
        except Exception as e:
            logger.warning(f"Failed to initialize window detector: {e}")
            self.window_detector = None

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

    def get_window_at_position(self, x: int, y: int) -> Optional[WindowInfo]:
        """
        Get window information at the specified coordinates.

        Args:
            x: X coordinate in screen space
            y: Y coordinate in screen space

        Returns:
            WindowInfo object or None if detection failed
        """
        if not self.window_detector:
            logger.error("Window detector not available")
            return None

        return self.window_detector.get_window_at_position(x, y)

    def capture_window_at_position(
        self, x: int, y: int, include_cursor: bool = True
    ) -> Optional[Image.Image]:
        """
        Capture the window at the specified coordinates.

        Args:
            x: X coordinate in screen space
            y: Y coordinate in screen space
            include_cursor: Whether to include the cursor in the capture

        Returns:
            PIL Image object or None if capture failed
        """
        window_info = self.get_window_at_position(x, y)
        if not window_info:
            logger.error(f"No window found at position ({x}, {y})")
            return None

        logger.info(f"Capturing window: {window_info.class_name} - {window_info.title}")

        # Get screen bounds
        screen_x, screen_y, screen_width, screen_height = self.get_screen_geometry()

        # Calculate the visible portion of the window
        # Start coordinates: where the window becomes visible on screen
        visible_x = max(window_info.x, screen_x)
        visible_y = max(window_info.y, screen_y)

        # End coordinates: where the window ends or screen ends, whichever comes first
        window_end_x = window_info.x + window_info.width
        window_end_y = window_info.y + window_info.height

        visible_end_x = min(window_end_x, screen_x + screen_width)
        visible_end_y = min(window_end_y, screen_y + screen_height)

        # Calculate visible dimensions
        visible_width = visible_end_x - visible_x
        visible_height = visible_end_y - visible_y

        # Ensure we have positive dimensions
        if visible_width <= 0 or visible_height <= 0:
            logger.error(
                f"Window has no visible area: {visible_width}x{visible_height}"
            )
            return None

        logger.debug(
            f"Window original: ({window_info.x}, {window_info.y}) {window_info.width}x{window_info.height}"
        )
        logger.debug(
            f"Capturing visible area: ({visible_x}, {visible_y}) {visible_width}x{visible_height}"
        )

        return self.capture_screen_area(
            visible_x,
            visible_y,
            visible_width,
            visible_height,
            include_cursor,
        )

    def capture_window_pure_content(
        self, window_id: int, include_cursor: bool = True
    ) -> Optional[tuple]:
        """
        Capture pure window content using XComposite extension.
        This captures the window's off-screen buffer, avoiding any overlapping elements.

        Args:
            window_id: X11 window ID
            include_cursor: Whether to include the cursor in the capture

        Returns:
            Tuple of (PIL Image, left_border, top_border) or None if capture failed
        """
        if not self.xcomposite:
            raise RuntimeError(
                "XComposite extension not available - pure window capture not supported"
            )

        if not self.window_detector:
            raise RuntimeError("Window detector not available")

        try:
            # Get window information
            visible_windows = self.window_detector.get_visible_windows()
            target_window = None

            for window in visible_windows:
                if window.window_id == window_id:
                    target_window = window
                    break

            if not target_window:
                raise RuntimeError(
                    f"Window with ID {window_id} not found or not visible"
                )

            logger.info(
                f"Capturing pure window content: {target_window.class_name} - {target_window.title}"
            )

            # Use alternative approach: Direct window contents with compositor bypass
            return self._capture_window_direct(target_window, include_cursor)

        except Exception as e:
            logger.error(
                f"Failed to capture pure window content for window {window_id}: {e}"
            )
            raise RuntimeError(f"Pure window capture failed: {e}")

    def _capture_window_direct(
        self, window_info: WindowInfo, include_cursor: bool
    ) -> Optional[tuple]:
        """
        Direct window content capture using Xlib with proper window handling.
        This bypasses compositor issues by directly accessing the window drawable.

        Returns:
            Tuple of (PIL Image, left_border, top_border) or None if capture failed
        """
        try:
            # Create window object from the window ID
            window_obj = self.display.create_resource_object(
                "window", window_info.window_id
            )

            # Get window attributes to ensure it's mappable
            attrs = window_obj.get_attributes()
            if getattr(attrs, "class", None) != X.InputOutput:
                logger.warning("Window may not be drawable (not InputOutput)")

            # Get window geometry to ensure we have correct dimensions
            geom = window_obj.get_geometry()
            full_width = geom.width
            full_height = geom.height

            logger.debug(f"Window geometry: {full_width}x{full_height}")

            # Get frame extents (including invisible GTK borders/shadows)
            left_border, right_border, top_border, bottom_border = (
                self.window_detector.get_window_frame_extents(window_obj)
            )

            logger.debug(
                f"Frame extents: left={left_border}, right={right_border}, "
                f"top={top_border}, bottom={bottom_border}"
            )

            # Calculate content-only geometry
            content_x = left_border
            content_y = top_border
            content_width = full_width - left_border - right_border
            content_height = full_height - top_border - bottom_border

            # Ensure content dimensions are valid
            if content_width <= 0 or content_height <= 0:
                logger.warning(
                    f"Invalid content dimensions: {content_width}x{content_height}, "
                    "falling back to full window"
                )
                content_x = 0
                content_y = 0
                content_width = full_width
                content_height = full_height
                left_border = right_border = top_border = bottom_border = 0

            logger.debug(f"Content geometry: {content_width}x{content_height} at ({content_x}, {content_y})")

            # Ensure window is mapped and visible
            if attrs.map_state != X.IsViewable:
                logger.warning("Window is not currently viewable")

            # Capture the window content directly (excluding borders)
            try:
                # Capture only the content area, excluding invisible borders
                raw_image = window_obj.get_image(
                    content_x, content_y, content_width, content_height, X.ZPixmap, 0xFFFFFFFF
                )

                # Convert to PIL Image using content dimensions
                if raw_image.depth == 24:
                    pil_image = Image.frombytes(
                        "RGB",
                        (content_width, content_height),
                        raw_image.data,
                        "raw",
                        "BGRX",
                    )
                elif raw_image.depth == 32:
                    pil_image = Image.frombytes(
                        "RGBA",
                        (content_width, content_height),
                        raw_image.data,
                        "raw",
                        "BGRA",
                    )
                elif raw_image.depth == 16:
                    # 16-bit color
                    pil_image = Image.frombytes(
                        "RGB",
                        (content_width, content_height),
                        raw_image.data,
                        "raw",
                        "BGR;16",
                    )
                else:
                    raise RuntimeError(f"Unsupported color depth: {raw_image.depth}")

                # Include cursor if requested (with border adjustment)
                if include_cursor:
                    pil_image = self._add_cursor_to_window_capture(
                        pil_image, window_info, left_border, top_border
                    )

                logger.info(
                    f"Successfully captured pure window content: {content_width}x{content_height} "
                    f"(excluding borders: L={left_border}, R={right_border}, T={top_border}, B={bottom_border})"
                )
                return (pil_image, left_border, top_border)

            except Exception as inner_e:
                # If direct window capture fails, try using the parent window or root window approach
                logger.warning(
                    f"Direct window capture failed: {inner_e}, trying alternative method"
                )
                return self._capture_window_area_fallback(
                    window_info, include_cursor
                )

        except Exception as e:
            logger.error(f"Window direct capture failed: {e}")
            raise RuntimeError(f"Direct window capture failed: {e}")

    def _capture_window_area_fallback(
        self, window_info: WindowInfo, include_cursor: bool
    ) -> Tuple[Optional[Image.Image], int, int]:
        """
        Fallback window capture using area-based capture technique.

        This is used when direct X11 pixmap capture fails. It captures the screen
        area where the window is located, which may include overlapping windows.
        Border detection is not available with this method.

        Args:
            window_info: Information about the window to capture
            include_cursor: Whether to include the cursor in the capture

        Returns:
            Tuple of (image, left_border, top_border) where borders are always 0
            since border detection is not available in area-based capture
        """
        try:
            # First, capture the window area normally (this will include overlaps)
            window_with_overlaps = self.capture_screen_area(
                window_info.x,
                window_info.y,
                window_info.width,
                window_info.height,
                include_cursor=False,
            )

            if not window_with_overlaps:
                raise RuntimeError("Failed to capture window area")

            logger.warning(
                "Using area-based fallback capture - may include overlapping windows "
                "(direct pixmap capture not available)"
            )

            if include_cursor:
                window_with_overlaps = self._add_cursor_to_pure_window(
                    window_with_overlaps, window_info
                )

            # Return consistent tuple format (borders unknown in area capture)
            return (window_with_overlaps, 0, 0)

        except Exception as e:
            logger.error(f"Area-based fallback capture failed: {e}")
            raise RuntimeError(f"Area-based fallback capture failed: {e}")

    def _add_cursor_to_pure_window(
        self, image: Image.Image, window_info: WindowInfo
    ) -> Image.Image:
        """
        Add cursor to pure window capture if cursor is within window bounds.

        Args:
            image: The captured window image
            window_info: Information about the captured window

        Returns:
            Image with cursor overlaid if cursor is within window
        """
        try:
            if not self.xfixes_cursor:
                return image

            # Get the actual cursor image using XFixes
            cursor_image = self.xfixes_cursor.get_cursor_image()

            if cursor_image and cursor_image.width > 0 and cursor_image.height > 0:
                # Get cursor position in screen coordinates
                cursor_screen_x = cursor_image.x
                cursor_screen_y = cursor_image.y

                # Convert to window-relative coordinates
                cursor_window_x = cursor_screen_x - window_info.x
                cursor_window_y = cursor_screen_y - window_info.y

                # Check if cursor is within the window bounds
                if (
                    0 <= cursor_window_x < window_info.width
                    and 0 <= cursor_window_y < window_info.height
                ):
                    # Convert cursor data to PIL Image
                    cursor_pil = self._convert_cursor_to_pil(cursor_image)

                    if cursor_pil:
                        # Calculate hotspot position relative to window
                        hotspot_x = cursor_window_x - cursor_image.xhot
                        hotspot_y = cursor_window_y - cursor_image.yhot

                        # Ensure we don't paste outside window bounds
                        if (
                            hotspot_x + cursor_image.width > 0
                            and hotspot_y + cursor_image.height > 0
                            and hotspot_x < window_info.width
                            and hotspot_y < window_info.height
                        ):
                            # Paste cursor onto the window image
                            if cursor_pil.mode == "RGBA":
                                image.paste(
                                    cursor_pil, (hotspot_x, hotspot_y), cursor_pil
                                )
                            else:
                                image.paste(cursor_pil, (hotspot_x, hotspot_y))

                            logger.debug(
                                f"Added cursor to pure window at ({hotspot_x}, {hotspot_y})"
                            )

        except Exception as e:
            logger.error(f"Failed to add cursor to pure window: {e}")

        return image

    def _add_cursor_to_window_capture(
        self, image: Image.Image, window_info: WindowInfo, left_border: int, top_border: int
    ) -> Image.Image:
        """
        Add cursor to window capture accounting for excluded borders.

        When capturing content-only (excluding invisible borders), cursor coordinates
        must be adjusted to account for the excluded border areas.

        Args:
            image: The captured window image (content-only, borders excluded)
            window_info: Information about the captured window (full geometry including borders)
            left_border: Left border size that was excluded from capture
            top_border: Top border size that was excluded from capture

        Returns:
            Image with cursor overlaid if cursor is within content area
        """
        try:
            if not self.xfixes_cursor:
                return image

            # Get the actual cursor image using XFixes
            cursor_image = self.xfixes_cursor.get_cursor_image()

            if cursor_image and cursor_image.width > 0 and cursor_image.height > 0:
                # Get cursor position in screen coordinates
                cursor_screen_x = cursor_image.x
                cursor_screen_y = cursor_image.y

                # Convert to window-relative coordinates (full window including borders)
                cursor_window_x = cursor_screen_x - window_info.x
                cursor_window_y = cursor_screen_y - window_info.y

                # Adjust for excluded borders to get content-relative coordinates
                cursor_content_x = cursor_window_x - left_border
                cursor_content_y = cursor_window_y - top_border

                # Get content dimensions (image is already content-only)
                content_width = image.width
                content_height = image.height

                # Check if cursor is within the content bounds
                if (
                    0 <= cursor_content_x < content_width
                    and 0 <= cursor_content_y < content_height
                ):
                    # Convert cursor data to PIL Image
                    cursor_pil = self._convert_cursor_to_pil(cursor_image)

                    if cursor_pil:
                        # Calculate hotspot position relative to content area
                        hotspot_x = cursor_content_x - cursor_image.xhot
                        hotspot_y = cursor_content_y - cursor_image.yhot

                        # Ensure we don't paste outside content bounds
                        if (
                            hotspot_x + cursor_image.width > 0
                            and hotspot_y + cursor_image.height > 0
                            and hotspot_x < content_width
                            and hotspot_y < content_height
                        ):
                            # Paste cursor onto the content image
                            if cursor_pil.mode == "RGBA":
                                image.paste(
                                    cursor_pil, (hotspot_x, hotspot_y), cursor_pil
                                )
                            else:
                                image.paste(cursor_pil, (hotspot_x, hotspot_y))

                            logger.debug(
                                f"Added cursor to content area at ({hotspot_x}, {hotspot_y}) "
                                f"(adjusted for borders: L={left_border}, T={top_border})"
                            )

        except Exception as e:
            logger.error(f"Failed to add cursor to content area: {e}")

        return image

    def capture_window_at_position_pure(
        self, x: int, y: int, include_cursor: bool = True
    ) -> Optional[Image.Image]:
        """
        Capture pure window content at the specified coordinates using XComposite.

        Args:
            x: X coordinate in screen space
            y: Y coordinate in screen space
            include_cursor: Whether to include the cursor in the capture

        Returns:
            PIL Image object or None if capture failed
        """
        window_info = self.get_window_at_position(x, y)
        if not window_info:
            logger.error(f"No window found at position ({x}, {y})")
            return None

        # Use direct capture method since we have the window info
        return self._capture_window_direct_with_info(window_info, include_cursor)

    def _capture_window_direct_with_info(
        self, window_info: WindowInfo, include_cursor: bool
    ) -> Optional[Image.Image]:
        """
        Capture pure window content using window info directly.
        This bypasses the need to find the window in visible windows list.
        """
        if not self.xcomposite:
            logger.warning("XComposite not available for pure window capture")
            # Still try direct capture without XComposite

        logger.info(
            f"Capturing pure window content: {window_info.class_name} - {window_info.title}"
        )

        try:
            return self._capture_window_direct(window_info, include_cursor)
        except Exception as e:
            logger.error(f"Failed to capture pure window content: {e}")
            raise RuntimeError(f"Pure window capture failed: {e}")

    def capture_window_by_id(
        self, window_id: int, include_cursor: bool = True
    ) -> Optional[Image.Image]:
        """
        Capture a specific window by its ID.

        Args:
            window_id: X11 window ID
            include_cursor: Whether to include the cursor in the capture

        Returns:
            PIL Image object or None if capture failed
        """
        if not self.window_detector:
            logger.error("Window detector not available")
            return None

        try:
            # Find the window in our visible windows list
            visible_windows = self.window_detector.get_visible_windows()
            target_window = None

            for window in visible_windows:
                if window.window_id == window_id:
                    target_window = window
                    break

            if not target_window:
                logger.error(f"Window with ID {window_id} not found or not visible")
                return None

            logger.info(
                f"Capturing window by ID: {target_window.class_name} - {target_window.title}"
            )

            return self.capture_screen_area(
                target_window.x,
                target_window.y,
                target_window.width,
                target_window.height,
                include_cursor,
            )

        except Exception as e:
            logger.error(f"Failed to capture window by ID {window_id}: {e}")
            return None

    def get_visible_windows(self) -> List[WindowInfo]:
        """
        Get a list of all visible windows.

        Returns:
            List of WindowInfo objects
        """
        if not self.window_detector:
            logger.error("Window detector not available")
            return []

        return self.window_detector.get_visible_windows()

    def save_screenshot(
        self,
        image: Image.Image,
        directory: str = None,
        filename: str = None,
        capture_type: str = "full",
    ) -> Tuple[str, int, str]:
        """
        Save screenshot to file with timestamp naming.

        Uses two-stage save strategy:
        1. Quick save to cache (for instant clipboard access)
        2. Optimized save to screenshots folder (in background)

        Args:
            image: PIL Image to save
            directory: Directory to save to (defaults to ~/Pictures/Screenshots)
            filename: Custom filename (defaults to timestamp format)
            capture_type: Type of capture for suffix ('win', 'full', 'area')

        Returns:
            Tuple of (final_filepath, file_size_bytes, cache_filepath)
            - final_filepath: Where the optimized file will be saved (for display/notification)
            - file_size_bytes: Size of the unoptimized cache file
            - cache_filepath: Path to cache file (for clipboard - stable reference)
        """
        # TWO-STAGE SAVE STRATEGY:
        # Stage 1: Quick save to cache for instant clipboard access

        # Get cache path (always same filename)
        cache_filepath = CaptiXPaths.get_cache_screenshot_path()
        cache_dir = CaptiXPaths.get_cache_dir()

        # Create cache directory if it doesn't exist
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        # Remove old cached file if it exists (cleanup from previous screenshot)
        if os.path.exists(cache_filepath):
            try:
                os.remove(cache_filepath)
                logger.debug(f"Removed old cached screenshot: {cache_filepath}")
            except OSError as e:
                logger.warning(f"Failed to remove old cache file: {e}")

        try:
            # Save unoptimized to cache (instant save)
            image.save(cache_filepath, "PNG", optimize=False)

            # Get cache file size
            file_size = os.path.getsize(cache_filepath)

            logger.info(f"Screenshot cached (quick): {cache_filepath} ({file_size} bytes)")

            # Stage 2: Set up final directory and filename for optimized save
            if directory is None:
                directory = CaptiXPaths.get_screenshots_dir()

            # Create final directory if it doesn't exist
            Path(directory).mkdir(parents=True, exist_ok=True)

            # Generate final filename if not provided
            if filename is None:
                filename = CaptiXPaths.generate_screenshot_filename(capture_type)

            # Ensure .png extension
            if not filename.lower().endswith('.png'):
                filename += '.png'

            final_filepath = os.path.join(directory, filename)

            # Launch background thread to save optimized version to final location
            # Use daemon thread so it doesn't block app exit
            optimization_thread = threading.Thread(
                target=self._save_optimized_background,
                args=(cache_filepath, final_filepath, file_size),
                daemon=True,
                name=f"SaveOptimized-{os.path.basename(final_filepath)}"
            )
            optimization_thread.start()
            logger.debug(f"Background optimization started: {cache_filepath} -> {final_filepath}")

            # Return both paths: final for display, cache for clipboard
            return final_filepath, file_size, cache_filepath

        except (OSError, IOError, PermissionError) as e:
            logger.error(f"Failed to save screenshot to cache {cache_filepath}: {e}")
            raise

    def _save_optimized_background(self, cache_filepath: str, final_filepath: str, original_size: int):
        """
        Save optimized screenshot from cache to final destination in background.

        This method runs in a background thread to read from the cache file,
        optimize it, and save to the final screenshots directory.

        Args:
            cache_filepath: Path to the cached (unoptimized) screenshot
            final_filepath: Path where optimized screenshot should be saved
            original_size: File size of unoptimized cache file (for logging)
        """
        try:
            # Verify cache file still exists
            if not os.path.exists(cache_filepath):
                logger.debug(f"Skipping optimization - cache file no longer exists: {cache_filepath}")
                return

            # Open the cached image
            logger.debug(f"Starting optimization: {cache_filepath} -> {final_filepath}")
            image = Image.open(cache_filepath)

            # Save optimized version to final destination
            image.save(final_filepath, "PNG", optimize=True)

            # Get optimized file size
            optimized_size = os.path.getsize(final_filepath)

            # Calculate space saved
            space_saved = original_size - optimized_size
            percent_saved = (space_saved / original_size * 100) if original_size > 0 else 0

            logger.info(
                f"Screenshot saved (optimized): {final_filepath} "
                f"({original_size} -> {optimized_size} bytes, "
                f"saved {space_saved} bytes / {percent_saved:.1f}%)"
            )

        except FileNotFoundError:
            logger.debug(f"Optimization skipped - cache file deleted: {cache_filepath}")
        except PermissionError as e:
            logger.warning(f"Optimization failed - permission denied for {final_filepath}: {e}")
        except OSError as e:
            # Catch disk full, I/O errors, etc.
            logger.warning(f"Optimization failed - OS error for {final_filepath}: {e}")
        except Exception as e:
            # Catch any other unexpected errors (corrupted image, etc.)
            logger.warning(f"Optimization failed: {cache_filepath} -> {final_filepath}: {e}")

    def cleanup(self):
        """Clean up X11 resources."""
        try:
            if self.xfixes_cursor:
                self.xfixes_cursor.close()
            if self.xcomposite:
                self.xcomposite.close()
            if self.window_detector:
                self.window_detector.cleanup()
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
    show_notification: bool = True,
) -> Tuple[str, int]:
    """
    Convenient function to capture a screenshot.

    Args:
        x, y, width, height: Area to capture (None for full screen)
        save_path: Where to save (None for default location)
        include_cursor: Whether to include cursor
        copy_to_clipboard: Whether to copy to clipboard (default: True)
        show_notification: Whether to show desktop notification (default: True)

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

        # Save the screenshot with appropriate type
        if x is not None and y is not None and width is not None and height is not None:
            capture_type = "area"
        else:
            capture_type = "full"
        final_path, file_size, cache_path = capture.save_screenshot(
            image, save_path, capture_type=capture_type
        )

        # Copy to clipboard if requested (use cache path - stable reference)
        if copy_to_clipboard:
            try:
                if copy_image_to_clipboard(cache_path):
                    logger.info("Screenshot copied to clipboard")
                else:
                    logger.warning("Failed to copy screenshot to clipboard")
            except Exception as e:
                logger.warning(f"Clipboard copy failed: {e}")

        # Show notification if requested (use final path for display)
        if show_notification:
            try:
                notify_screenshot_saved(final_path, file_size)
            except Exception as e:
                logger.warning(f"Failed to show notification: {e}")

        return final_path, file_size

    finally:
        capture.cleanup()


def capture_window_at_position(
    x: int,
    y: int,
    save_path: str = None,
    include_cursor: bool = True,
    copy_to_clipboard: bool = True,
    show_notification: bool = True,
) -> Tuple[str, int]:
    """
    Capture the window at the specified coordinates.

    Args:
        x: X coordinate in screen space
        y: Y coordinate in screen space
        save_path: Where to save (None for default location)
        include_cursor: Whether to include cursor
        copy_to_clipboard: Whether to copy to clipboard (default: True)
        show_notification: Whether to show desktop notification (default: True)

    Returns:
        Tuple of (filepath, file_size_bytes)
    """
    capture = ScreenCapture()

    try:
        # Capture window at position
        image = capture.capture_window_at_position(x, y, include_cursor)

        if image is None:
            raise RuntimeError(f"Failed to capture window at position ({x}, {y})")

        # Save the screenshot
        final_path, file_size, cache_path = capture.save_screenshot(
            image, save_path, capture_type="win"
        )

        # Copy to clipboard if requested (use cache path - stable reference)
        if copy_to_clipboard:
            try:
                if copy_image_to_clipboard(cache_path):
                    logger.info("Screenshot copied to clipboard")
                else:
                    logger.warning("Failed to copy screenshot to clipboard")
            except Exception as e:
                logger.warning(f"Clipboard copy failed: {e}")

        # Show notification if requested (use final path for display)
        if show_notification:
            try:
                notify_screenshot_saved(final_path, file_size)
            except Exception as e:
                logger.warning(f"Failed to show notification: {e}")

        return final_path, file_size

    finally:
        capture.cleanup()


def get_window_info_at_position(x: int, y: int) -> Optional[WindowInfo]:
    """
    Get information about the window at the specified coordinates.

    Args:
        x: X coordinate in screen space
        y: Y coordinate in screen space

    Returns:
        WindowInfo object or None if no window found
    """
    capture = ScreenCapture()

    try:
        return capture.get_window_at_position(x, y)
    finally:
        capture.cleanup()


def list_visible_windows() -> List[WindowInfo]:
    """
    Get a list of all visible windows.

    Returns:
        List of WindowInfo objects
    """
    capture = ScreenCapture()

    try:
        return capture.get_visible_windows()
    finally:
        capture.cleanup()


def capture_window_at_position_pure(
    x: int,
    y: int,
    save_path: str = None,
    include_cursor: bool = True,
    copy_to_clipboard: bool = True,
    show_notification: bool = True,
) -> Tuple[str, int]:
    """
    Capture pure window content at the specified coordinates using XComposite.
    This captures only the window content without any overlapping elements.

    Args:
        x: X coordinate in screen space
        y: Y coordinate in screen space
        save_path: Where to save (None for default location)
        include_cursor: Whether to include cursor
        copy_to_clipboard: Whether to copy to clipboard (default: True)
        show_notification: Whether to show desktop notification (default: True)

    Returns:
        Tuple of (filepath, file_size_bytes)
    """
    capture = ScreenCapture()

    try:
        # Capture pure window content at position
        image = capture.capture_window_at_position_pure(x, y, include_cursor)

        if image is None:
            raise RuntimeError(
                f"Failed to capture pure window content at position ({x}, {y})"
            )

        # Save the screenshot
        final_path, file_size, cache_path = capture.save_screenshot(
            image, save_path, capture_type="win"
        )

        # Copy to clipboard if requested (use cache path - stable reference)
        if copy_to_clipboard:
            try:
                if copy_image_to_clipboard(cache_path):
                    logger.info("Screenshot copied to clipboard")
                else:
                    logger.warning("Failed to copy screenshot to clipboard")
            except Exception as e:
                logger.warning(f"Clipboard copy failed: {e}")

        # Show notification if requested (use final path for display)
        if show_notification:
            try:
                notify_screenshot_saved(final_path, file_size)
            except Exception as e:
                logger.warning(f"Failed to show notification: {e}")

        return final_path, file_size

    finally:
        capture.cleanup()


if __name__ == "__main__":
    # Test the capture functionality
    print("Testing screen capture...")
    try:
        # Test area capture (existing functionality)
        print("\n1. Testing area capture (full screen)...")
        filepath, size = capture_screenshot()
        print(f"Screenshot saved: {filepath}")
        print(f"File size: {size} bytes ({size/1024:.1f} KB)")

        # Test pure window capture if XComposite is available
        print("\n2. Testing pure window capture...")
        capture = ScreenCapture()
        if capture.xcomposite:
            print("XComposite available - testing pure window capture")
            # Get first visible window for testing
            windows = capture.get_visible_windows()
            if windows:
                test_window = windows[0]
                print(
                    f"Testing with window: {test_window.class_name} - {test_window.title}"
                )

                try:
                    # Test pure window capture
                    pure_image = capture.capture_window_pure_content(
                        test_window.window_id
                    )
                    if pure_image:
                        # Save test image
                        test_filepath, test_size = capture.save_screenshot(
                            pure_image,
                            filename="test_pure_window.png",
                            capture_type="win",
                        )
                        print(f"Pure window capture saved: {test_filepath}")
                        print(
                            f"File size: {test_size} bytes ({test_size / 1024:.1f} KB)"
                        )
                    else:
                        print("Pure window capture returned None")
                except Exception as e:
                    print(f"Pure window capture failed: {e}")
            else:
                print("No visible windows found for testing")
        else:
            print("XComposite not available - pure window capture disabled")
            print("You can still use regular window capture (with potential overlaps)")

        capture.cleanup()

    except Exception as e:
        print(f"Error: {e}")