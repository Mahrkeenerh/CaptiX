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
            "_GTK_FRAME_EXTENTS",  # Must be checked BEFORE _NET_FRAME_EXTENTS
            "_NET_FRAME_EXTENTS",
            "_NET_WM_WINDOW_TYPE",
            "_NET_WM_WINDOW_TYPE_DESKTOP",
            "_NET_WM_WINDOW_TYPE_DOCK",
            "_NET_WM_WINDOW_TYPE_TOOLBAR",
            "_NET_WM_WINDOW_TYPE_MENU",
            "_NET_WM_WINDOW_TYPE_UTILITY",
            "_NET_WM_WINDOW_TYPE_SPLASH",
            "_NET_WM_WINDOW_TYPE_DIALOG",
            "_NET_WM_WINDOW_TYPE_NORMAL",
            "WM_CLASS",
            "WM_NAME",
            "_NET_WM_NAME",
            # Workspace filtering atoms (Phase 4.11)
            "_NET_CURRENT_DESKTOP",
            "_NET_WM_DESKTOP",
            "_NET_NUMBER_OF_DESKTOPS",
            # Window state atoms for minimized detection
            "_NET_WM_STATE",
            "_NET_WM_STATE_HIDDEN",
            "_NET_WM_STATE_MINIMIZED",
            "WM_STATE",
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
            # Window queries can fail with BadWindow (destroyed), XError, RuntimeError, etc.
            # Windows can be closed/moved between query and access. Broad handling required.
            logger.error(f"Failed to get window at position ({x}, {y}): {e}")
            return None

    def get_window_at_position_excluding(
        self, x: int, y: int, exclude_window_id: Optional[int] = None
    ) -> Optional[WindowInfo]:
        """
        Get the topmost window at the specified screen coordinates, excluding specified window IDs.

        This method walks the X11 window stack to find windows beneath excluded windows.

        Args:
            x: X coordinate in screen space
            y: Y coordinate in screen space
            exclude_window_id: Window ID to exclude from detection (e.g., overlay window)

        Returns:
            WindowInfo object or None if no window found
        """
        if exclude_window_id is None:
            # No exclusion needed, use regular detection
            return self.get_window_at_position(x, y)

        try:
            # Get all child windows in Z-order (top to bottom)
            windows_in_stack = self._get_window_stack()

            for window in windows_in_stack:
                try:
                    # Skip the excluded window
                    if window.id == exclude_window_id:
                        logger.debug(
                            f"Skipping excluded window ID: {exclude_window_id}"
                        )
                        continue

                    # Check if this window contains the coordinates
                    if self._window_contains_point(window, x, y):
                        # Get detailed window info
                        window_info = self._get_window_info(window)
                        if window_info:
                            return window_info

                except (BadWindow, BadMatch):
                    # Skip invalid windows
                    continue

            # No window found, return root window info
            return self._create_root_window_info()

        except Exception as e:
            logger.error(
                f"Failed to get window at position excluding {exclude_window_id}: {e}"
            )
            return None

    def _get_window_stack(self) -> list:
        """
        Get all windows in the X11 window stack (Z-order).

        Returns:
            List of X11 window objects in top-to-bottom order
        """
        try:
            # Query all child windows of root
            result = self.root.query_tree()
            children = result.children

            # Return in reverse order (top to bottom in Z-order)
            # X11 returns children in bottom-to-top order
            return list(reversed(children))

        except Exception as e:
            logger.error(f"Failed to get window stack: {e}")
            return []

    def _window_contains_point(self, window, x: int, y: int) -> bool:
        """
        Check if a window contains the specified point.

        Args:
            window: X11 window object
            x: X coordinate in screen space
            y: Y coordinate in screen space

        Returns:
            True if window contains the point, False otherwise
        """
        try:
            # Check if window is visible and valid
            attrs = window.get_attributes()
            if attrs.win_class != X.InputOutput or attrs.map_state != X.IsViewable:
                return False

            # Get window geometry
            geom = window.get_geometry()

            # Get absolute coordinates using the proper hierarchy walking method
            # This fixes the negative coordinate issue with decorated windows
            window_x, window_y = self._get_absolute_coordinates(window)

            # Debug log for collision detection
            contains = (
                window_x <= x < window_x + geom.width
                and window_y <= y < window_y + geom.height
            )

            if contains:
                try:
                    # Get window info for debug
                    window_info = self._get_window_info(window)
                    title = window_info.title if window_info else "Unknown"
                    logger.debug(
                        f"Window '{title}' at ({window_x},{window_y}) {geom.width}x{geom.height} contains point ({x},{y})"
                    )
                except Exception:
                    logger.debug(
                        f"Window at ({window_x},{window_y}) {geom.width}x{geom.height} contains point ({x},{y})"
                    )

            return contains

        except (BadWindow, BadMatch):
            return False
        except Exception as e:
            logger.debug(f"Error checking if window contains point: {e}")
            return False

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
    
    def get_window_frame_extents(self, window) -> Tuple[int, int, int, int]:
        """
        Get frame extents (window decorations) for a window.

        This method checks for both GTK client-side decorations (_GTK_FRAME_EXTENTS)
        and standard window manager decorations (_NET_FRAME_EXTENTS).

        GTK applications with client-side decorations often have invisible borders
        for drop shadows and resize areas. These must be detected to capture only
        the visible window content.

        Args:
            window: X11 window object

        Returns:
            Tuple of (left, right, top, bottom) border sizes in pixels
        """
        # 1. First try _GTK_FRAME_EXTENTS for GTK apps with client-side decorations
        #    This property describes invisible borders/shadows around GTK windows
        try:
            if '_GTK_FRAME_EXTENTS' in self._atoms:
                prop = window.get_property(
                    self._atoms['_GTK_FRAME_EXTENTS'],
                    Xatom.CARDINAL,
                    0, 4
                )

                if prop and prop.value and len(prop.value) >= 4:
                    left, right, top, bottom = prop.value[:4]
                    logger.debug(f"GTK frame extents detected: left={left}, right={right}, top={top}, bottom={bottom}")
                    return (left, right, top, bottom)
        except Exception as e:
            logger.debug(f"Failed to get GTK frame extents: {e}")

        # 2. Try _NET_FRAME_EXTENTS property (standard window manager decorations)
        try:
            if '_NET_FRAME_EXTENTS' in self._atoms:
                prop = window.get_property(
                    self._atoms['_NET_FRAME_EXTENTS'],
                    Xatom.CARDINAL,
                    0, 4
                )

                if prop and prop.value and len(prop.value) >= 4:
                    left, right, top, bottom = prop.value[:4]
                    logger.debug(f"NET frame extents detected: left={left}, right={right}, top={top}, bottom={bottom}")
                    return (left, right, top, bottom)
        except Exception as e:
            logger.debug(f"Failed to get NET frame extents: {e}")

        # 3. Fallback: estimate from window geometry
        try:
            geom = window.get_geometry()

            # If window has negative coordinates, it has borders
            left_border = max(0, -geom.x) if geom.x < 0 else 0
            top_border = max(0, -geom.y) if geom.y < 0 else 0

            # If left border detected, assume uniform borders (common pattern)
            if left_border > 0:
                logger.debug(f"Estimated uniform borders from geometry: {left_border}px")
                return (left_border, left_border, left_border, left_border)

            # If only top border, it's likely a title bar
            if top_border > 0:
                logger.debug(f"Estimated title bar from geometry: {top_border}px")
                return (0, 0, top_border, 0)
        except Exception as e:
            logger.debug(f"Failed to estimate frame extents: {e}")

        # No borders detected
        return (0, 0, 0, 0)

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

    def get_current_workspace(self) -> Optional[int]:
        """Get the current workspace/desktop number."""
        try:
            if "_NET_CURRENT_DESKTOP" not in self._atoms:
                logger.debug("_NET_CURRENT_DESKTOP atom not available")
                return None

            prop = self.root.get_full_property(
                self._atoms["_NET_CURRENT_DESKTOP"], Xatom.CARDINAL
            )

            if prop and prop.value:
                current_desktop = prop.value[0]
                logger.debug(f"Current workspace: {current_desktop}")
                return current_desktop

        except Exception as e:
            logger.debug(f"Failed to get current workspace: {e}")

        return None

    def get_window_workspace(self, window) -> Optional[int]:
        """Get the workspace/desktop number for a specific window."""
        try:
            if "_NET_WM_DESKTOP" not in self._atoms:
                return None

            prop = window.get_full_property(
                self._atoms["_NET_WM_DESKTOP"], Xatom.CARDINAL
            )

            if prop and prop.value:
                desktop = prop.value[0]
                # -1 means window is on all workspaces (sticky)
                return desktop

        except Exception as e:
            logger.debug(f"Failed to get window workspace: {e}")

        return None

    def is_window_minimized(self, window) -> bool:
        """Check if a window is minimized/hidden."""
        try:
            # Method 1: Check _NET_WM_STATE for hidden/minimized states
            if "_NET_WM_STATE" in self._atoms:
                prop = window.get_full_property(
                    self._atoms["_NET_WM_STATE"], Xatom.ATOM
                )

                if prop and prop.value:
                    states = prop.value

                    # Check for hidden or minimized states
                    hidden_atoms = []
                    if "_NET_WM_STATE_HIDDEN" in self._atoms:
                        hidden_atoms.append(self._atoms["_NET_WM_STATE_HIDDEN"])
                    if "_NET_WM_STATE_MINIMIZED" in self._atoms:
                        hidden_atoms.append(self._atoms["_NET_WM_STATE_MINIMIZED"])

                    for state in states:
                        if state in hidden_atoms:
                            return True

            # Method 2: Fallback to WM_STATE (older ICCCM standard)
            if "WM_STATE" in self._atoms:
                prop = window.get_full_property(
                    self._atoms["WM_STATE"], self._atoms["WM_STATE"]
                )

                if prop and prop.value:
                    wm_state = prop.value[0]
                    # WM_STATE values: 0=Withdrawn, 1=Normal, 3=Iconic (minimized)
                    if wm_state == 3:  # Iconic state = minimized
                        return True

        except Exception as e:
            logger.debug(f"Failed to check if window is minimized: {e}")

        return False

    def is_window_too_small(self, window_info: WindowInfo, min_size: int = 200) -> bool:
        """Check if window is too small to be a useful screenshot target."""
        return window_info.width < min_size or window_info.height < min_size

    def filter_windows_for_capture(self, windows: List[WindowInfo]) -> List[WindowInfo]:
        """Filter windows to only include those suitable for capture."""
        current_workspace = self.get_current_workspace()
        filtered_windows = []

        logger.info(
            f"Filtering {len(windows)} windows (current workspace: {current_workspace})"
        )

        for window_info in windows:
            try:
                # Skip root windows
                if window_info.is_root:
                    continue

                # Skip very small windows
                if self.is_window_too_small(window_info):
                    continue

                # Get the actual X11 window object for further checks
                try:
                    window_obj = self.display.create_resource_object(
                        "window", window_info.window_id
                    )
                except Exception as e:
                    logger.debug(
                        f"Failed to create window object for {window_info.title}: {e}"
                    )
                    continue

                # Check if window is minimized
                if self.is_window_minimized(window_obj):
                    continue

                # Skip tiny windows (1x1 system windows)
                if window_info.width <= 1 or window_info.height <= 1:
                    logger.debug(
                        f"Skipping tiny window {window_info.title}: {window_info.width}x{window_info.height}"
                    )
                    continue

                # Check workspace if available
                if current_workspace is not None:
                    window_workspace = self.get_window_workspace(window_obj)
                    if window_workspace is not None:
                        # Only include windows on current workspace (exclude sticky windows on all workspaces)
                        # Note: window_workspace can be -1 (0xFFFFFFFF) for sticky windows
                        if window_workspace != current_workspace:
                            logger.debug(
                                f"Skipping window {window_info.title}: workspace {window_workspace} != current {current_workspace}"
                            )
                            continue
                    # If window_workspace is None, include the window (no workspace info available)

                # Window passed all filters
                filtered_windows.append(window_info)

            except Exception as e:
                logger.warning(f"Error filtering window {window_info.title}: {e}")
                continue

        logger.info(
            f"Filtered windows: {len(filtered_windows)} out of {len(windows)} windows"
        )
        return filtered_windows

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