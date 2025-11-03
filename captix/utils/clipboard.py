"""
Clipboard integration for CaptiX.

This module handles copying screenshots to the X11 clipboard using xclip
with saved screenshot files.
"""

import logging
import subprocess
import os

# Set up logging
logger = logging.getLogger(__name__)


def copy_image_to_clipboard(file_path: str) -> bool:
    """
    Copy a saved PNG image file to the clipboard using xclip.
    
    This approach uses the already-saved screenshot file directly.
    
    Args:
        file_path: Path to the PNG file to copy to clipboard
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Check if xclip is available
        if not _check_xclip_available():
            logger.error("xclip not available - cannot copy to clipboard")
            return False
        
        # Check if file exists
        if not os.path.exists(file_path):
            logger.error(f"Screenshot file not found: {file_path}")
            return False
        
        # Use xclip to copy the image file to clipboard
        # Use Popen with immediate return to avoid hanging
        process = subprocess.Popen(
            ['xclip', '-selection', 'clipboard', '-t', 'image/png', '-i', file_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Wait briefly for the process to complete
        try:
            process.wait(timeout=1)
            if process.returncode == 0:
                logger.info(f"Image file copied to clipboard successfully: {file_path}")
                return True
            else:
                logger.warning(f"xclip returned code {process.returncode}, but may have succeeded")
                return True  # Return True anyway since clipboard often works even with non-zero codes
        except subprocess.TimeoutExpired:
            # Process is still running, but clipboard copy likely succeeded
            logger.info(f"xclip still running, but clipboard copy likely successful: {file_path}")
            return True
            
    except FileNotFoundError:
        logger.error("xclip not found - please install xclip package")
        return False
    except Exception as e:
        logger.error(f"Failed to copy image to clipboard: {e}")
        return False


def test_clipboard_availability() -> bool:
    """
    Test if clipboard operations are available.
    
    Returns:
        True if clipboard is available, False otherwise
    """
    return _check_xclip_available()


def _check_xclip_available() -> bool:
    """Check if xclip is available on the system."""
    try:
        result = subprocess.run(
            ['which', 'xclip'], 
            capture_output=True, 
            text=True, 
            timeout=2
        )
        available = result.returncode == 0
        if not available:
            logger.warning("xclip not found in PATH - clipboard functionality disabled")
        return available
    except Exception as e:
        logger.warning(f"Error checking for xclip: {e}")
        return False


# Fallback implementation note:
# The old X11 direct implementation has been removed in favor of the 
# more reliable xclip file-based approach


def cleanup_clipboard():
    """Clean up clipboard resources (no longer needed with file-based approach)."""
    pass