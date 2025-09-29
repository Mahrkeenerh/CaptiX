"""
Window detection functionality for CaptiX.

This module handles X11 window detection and geometry calculation including:
- Window detection at specific coordinates
- Window geometry calculation with decorations
- Root window (desktop) detection
- Multi-window manager support
"""

import logging
from typing import Tuple, Optional, List, NamedTuple
from Xlib import display, X, Xatom
from Xlib.error import BadWindow, BadMatch

# Set up logging
logger = logging.getLogger(__name__)


class WindowInfo(NamedTuple):
    """Container for window information."""
    window_id: int
    x: int
    y: int
    width: int
    height: int
    class_name: str
    title: str
    is_root: bool


class WindowDetector:
    """Handles X11 window detection and geometry operations."""
    
    def __init__(self):
        """Initialize the window detector."""
        self.display = display.Display()
        self.screen = self.display.screen()
        self.root = self.screen.root
        
        # Cache for atoms we'll need
        self._atoms = {}
        self._init_atoms()
    
    def _init_atoms(self):
        """Initialize commonly used X11 atoms."""
        atom_names = [
            '_NET_FRAME_EXTENTS',
            '_NET_WM_WINDOW_TYPE',
            '_NET_WM_WINDOW_TYPE_DESKTOP',
            '_NET_WM_WINDOW_TYPE_DOCK',
            '_NET_WM_WINDOW_TYPE_TOOLBAR',
            '_NET_WM_WINDOW_TYPE_MENU',
            '_NET_WM_WINDOW_TYPE_UTILITY',
            '_NET_WM_WINDOW_TYPE_SPLASH',
            '_NET_WM_WINDOW_TYPE_DIALOG',
            '_NET_WM_WINDOW_TYPE_NORMAL',
            'WM_CLASS',
            'WM_NAME',
            '_NET_WM_NAME'
        ]
        
        for atom_name in atom_names:
            try:
                self._atoms[atom_name] = self.display.intern_atom(atom_name)
            except Exception as e:
                logger.debug(f"Failed to intern atom {atom_name}: {e}")
    
    def get_window_at_position(self, x: int, y: int) -> Optional[WindowInfo]:
        """
        Get the topmost window at the specified screen coordinates.
        
        Args:
            x: X coordinate in screen space
            y: Y coordinate in screen space
            
        Returns:
            WindowInfo object or None if no window found
        """
        try:
            # Start from root window and traverse down
            current_window = self.root
            
            while True:
                # Translate coordinates to find child window
                result = current_window.translate_coords(self.root, x, y)
                child_window = result.child
                
                if child_window == X.NONE:
                    # No child window, current window is the target
                    break
                
                # Check if this child window is actually visible and valid
                try:
                    child_attrs = child_window.get_attributes()
                    if child_attrs.win_class == X.InputOutput and child_attrs.map_state == X.IsViewable:
                        current_window = child_window
                        # Update coordinates relative to this window
                        x, y = result.x, result.y
                    else:
                        # Child is not visible, stick with current
                        break
                except (BadWindow, BadMatch):
                    # Invalid window, stick with current
                    break
            
            # Check if we ended up at the root window
            if current_window == self.root:
                return self._create_root_window_info()
            
            # Get detailed information about the window
            return self._get_window_info(current_window)
            
        except Exception as e:
            logger.error(f"Failed to get window at position ({x}, {y}): {e}")
            return None
    
    def _create_root_window_info(self) -> WindowInfo:
        """Create WindowInfo for the root window (desktop)."""
        try:
            geometry = self.root.get_geometry()
            return WindowInfo(
                window_id=self.root.id,
                x=0,
                y=0,
                width=geometry.width,
                height=geometry.height,
                class_name="Desktop",
                title="Desktop",
                is_root=True
            )
        except Exception as e:
            logger.error(f"Failed to get root window info: {e}")
            # Fallback with reasonable defaults
            return WindowInfo(
                window_id=self.root.id,
                x=0,
                y=0,
                width=1920,  # Reasonable fallback
                height=1080,
                class_name="Desktop",
                title="Desktop",
                is_root=True
            )
    
    def _get_window_info(self, window) -> Optional[WindowInfo]:
        """
        Extract detailed information from a window.
        
        Args:
            window: X11 window object
            
        Returns:
            WindowInfo object or None if failed
        """
        try:
            # Get basic geometry
            geometry = window.get_geometry()
            
            # Get absolute coordinates using hierarchy walk
            abs_x, abs_y = self._get_absolute_coordinates(window)
            
            # Use window dimensions
            width = geometry.width
            height = geometry.height
            
            # Get window class and title
            class_name = self._get_window_class(window)
            title = self._get_window_title(window)
            
            # Check if this should be considered a "capturable" window
            if not self._is_capturable_window(window):
                logger.debug(f"Window {window.id} is not capturable, treating as desktop")
                return self._create_root_window_info()
            
            return WindowInfo(
                window_id=window.id,
                x=abs_x,
                y=abs_y,
                width=width,
                height=height,
                class_name=class_name,
                title=title,
                is_root=False
            )
            
        except Exception as e:
            logger.error(f"Failed to get window info for window {window.id}: {e}")
            return None
    
    def _get_absolute_coordinates(self, window) -> Tuple[int, int]:
        """
        Get the absolute screen coordinates of a window by walking up the window hierarchy.
        
        This method properly handles window manager decorations by accumulating
        coordinates from the target window up to the root window.
        
        Args:
            window: X11 window object
            
        Returns:
            Tuple of (x, y) absolute screen coordinates
        """
        try:
            total_x = 0
            total_y = 0
            current_window = window
            
            # Walk up the window hierarchy
            while True:
                try:
                    # Get current window geometry
                    geom = current_window.get_geometry()
                    total_x += geom.x
                    total_y += geom.y
                    
                    # Get parent window
                    tree = current_window.query_tree()
                    parent = tree.parent
                    
                    # If we reached the root, we're done
                    if not parent or parent.id == self.root.id:
                        break
                    
                    current_window = parent
                    
                except Exception as e:
                    logger.debug(f"Error in hierarchy walk: {e}")
                    break
            
            return total_x, total_y
            
        except Exception as e:
            logger.warning(f"Failed to calculate absolute coordinates, falling back to translate_coords: {e}")
            # Fallback to translate_coords method
            try:
                coords = window.translate_coords(self.root, 0, 0)
                return coords.x, coords.y
            except Exception as e2:
                logger.error(f"Fallback method also failed: {e2}")
                # Last resort: use window geometry
                geom = window.get_geometry()
                return geom.x, geom.y
    
    def _get_frame_extents(self, window) -> Optional[Tuple[int, int, int, int]]:
        """
        Get window frame extents (decorations) if available.
        
        Args:
            window: X11 window object
            
        Returns:
            Tuple of (left, right, top, bottom) extents or None
        """
        try:
            if '_NET_FRAME_EXTENTS' not in self._atoms:
                return None
            
            prop = window.get_property(
                self._atoms['_NET_FRAME_EXTENTS'],
                Xatom.CARDINAL,
                0, 4
            )
            
            if prop and prop.value and len(prop.value) >= 4:
                # _NET_FRAME_EXTENTS: left, right, top, bottom
                return (prop.value[0], prop.value[1], prop.value[2], prop.value[3])
                
        except Exception as e:
            logger.debug(f"Failed to get frame extents: {e}")
        
        return None
    
    def _get_window_class(self, window) -> str:
        """Get window class name."""
        try:
            if 'WM_CLASS' not in self._atoms:
                return "Unknown"
            
            prop = window.get_property(self._atoms['WM_CLASS'], Xatom.STRING, 0, 1024)
            if prop and prop.value:
                # WM_CLASS contains instance\0class\0
                class_data = prop.value.decode('utf-8', errors='ignore')
                parts = class_data.split('\0')
                if len(parts) >= 2:
                    return parts[1]  # Return the class name
                elif len(parts) >= 1:
                    return parts[0]  # Return the instance name
                    
        except Exception as e:
            logger.debug(f"Failed to get window class: {e}")
        
        return "Unknown"
    
    def _get_window_title(self, window) -> str:
        """Get window title, trying both _NET_WM_NAME and WM_NAME."""
        try:
            # Try _NET_WM_NAME first (UTF-8)
            if '_NET_WM_NAME' in self._atoms:
                prop = window.get_property(self._atoms['_NET_WM_NAME'], Xatom.STRING, 0, 1024)
                if prop and prop.value:
                    return prop.value.decode('utf-8', errors='ignore')
            
            # Fallback to WM_NAME
            if 'WM_NAME' in self._atoms:
                prop = window.get_property(self._atoms['WM_NAME'], Xatom.STRING, 0, 1024)
                if prop and prop.value:
                    return prop.value.decode('utf-8', errors='ignore')
                    
        except Exception as e:
            logger.debug(f"Failed to get window title: {e}")
        
        return "Untitled"
    
    def _is_capturable_window(self, window) -> bool:
        """
        Determine if a window should be capturable (not a dock, menu, etc.).
        
        Args:
            window: X11 window object
            
        Returns:
            True if window should be capturable
        """
        try:
            if '_NET_WM_WINDOW_TYPE' not in self._atoms:
                return True  # Default to capturable if we can't determine type
            
            prop = window.get_property(
                self._atoms['_NET_WM_WINDOW_TYPE'],
                Xatom.ATOM,
                0, 10
            )
            
            if not prop or not prop.value:
                return True  # No window type set, assume normal window
            
            # Check for non-capturable window types
            non_capturable_types = [
                '_NET_WM_WINDOW_TYPE_DESKTOP',
                '_NET_WM_WINDOW_TYPE_DOCK',
                '_NET_WM_WINDOW_TYPE_TOOLBAR',
                '_NET_WM_WINDOW_TYPE_MENU',
                '_NET_WM_WINDOW_TYPE_SPLASH'
            ]
            
            for window_type in prop.value:
                type_name = self.display.get_atom_name(window_type)
                if type_name in non_capturable_types:
                    logger.debug(f"Window {window.id} has non-capturable type: {type_name}")
                    return False
                    
        except Exception as e:
            logger.debug(f"Failed to check window type: {e}")
        
        return True
    
    def get_visible_windows(self) -> List[WindowInfo]:
        """
        Get a list of all visible, capturable windows.
        
        Returns:
            List of WindowInfo objects
        """
        windows = []
        
        try:
            # Get all child windows of root
            children = self.root.query_tree().children
            
            for child in children:
                try:
                    # Check if window is visible
                    attrs = child.get_attributes()
                    if attrs.win_class == X.InputOutput and attrs.map_state == X.IsViewable:
                        window_info = self._get_window_info(child)
                        if window_info and not window_info.is_root:
                            windows.append(window_info)
                except (BadWindow, BadMatch):
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to get visible windows: {e}")
        
        return windows
    
    def cleanup(self):
        """Clean up X11 resources."""
        try:
            self.display.close()
        except Exception as e:
            logger.warning(f"Error during window detector cleanup: {e}")


# Convenience functions for easy integration
def get_window_at_position(x: int, y: int) -> Optional[WindowInfo]:
    """
    Convenience function to get window at position.
    
    Args:
        x: X coordinate
        y: Y coordinate
        
    Returns:
        WindowInfo or None
    """
    detector = WindowDetector()
    try:
        return detector.get_window_at_position(x, y)
    finally:
        detector.cleanup()


def get_visible_windows() -> List[WindowInfo]:
    """
    Convenience function to get all visible windows.
    
    Returns:
        List of WindowInfo objects
    """
    detector = WindowDetector()
    try:
        return detector.get_visible_windows()
    finally:
        detector.cleanup()


if __name__ == "__main__":
    # Quick test of window detection functionality
    try:
        detector = WindowDetector()
        geometry = detector.root.get_geometry()
        center_x = geometry.width // 2
        center_y = geometry.height // 2
        
        window_info = detector.get_window_at_position(center_x, center_y)
        if window_info:
            print(f"Window at center: {window_info.class_name} - {window_info.title}")
        else:
            print("No window found at center")
            
        detector.cleanup()
        
    except Exception as e:
        print(f"Error during testing: {e}")