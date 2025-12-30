"""Centralized path management for CaptiX.

This module provides utilities for managing file paths and directories
used by CaptiX for screenshots and recordings.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Tuple


class CaptiXPaths:
    """Centralized path management for CaptiX.

    Provides consistent access to default directories and file naming
    conventions across the application.
    """

    # Default directories (will be expanded with os.path.expanduser)
    DEFAULT_SCREENSHOTS_DIR = "~/Gallery/Screenshots"
    DEFAULT_VIDEOS_DIR = "~/Gallery/Recordings"

    # File naming configuration
    SCREENSHOT_PREFIX = "sc"
    SCREENSHOT_EXTENSION = ".png"
    TIMESTAMP_FORMAT = "%Y-%m-%d_%H%M%S"
    MONTH_FOLDER_FORMAT = "%Y-%m"

    @staticmethod
    def get_screenshots_dir() -> str:
        """Get the default screenshots directory (expanded).

        Returns:
            str: Absolute path to screenshots directory with ~ expanded.
        """
        return os.path.expanduser(CaptiXPaths.DEFAULT_SCREENSHOTS_DIR)

    @staticmethod
    def get_videos_dir() -> str:
        """Get the default videos directory (expanded).

        Returns:
            str: Absolute path to videos directory with ~ expanded.
        """
        return os.path.expanduser(CaptiXPaths.DEFAULT_VIDEOS_DIR)

    @staticmethod
    def get_current_month_folder() -> str:
        """Get the current month folder name.

        Returns:
            str: Month folder name in format YYYY-MM (e.g., "2025-12").
        """
        return datetime.now().strftime(CaptiXPaths.MONTH_FOLDER_FORMAT)

    @staticmethod
    def get_screenshots_month_dir() -> str:
        """Get the screenshots directory with current month subfolder.

        Returns:
            str: Absolute path to screenshots month directory.
        """
        base_dir = CaptiXPaths.get_screenshots_dir()
        month_folder = CaptiXPaths.get_current_month_folder()
        return os.path.join(base_dir, month_folder)

    @staticmethod
    def get_videos_month_dir() -> str:
        """Get the videos directory with current month subfolder.

        Returns:
            str: Absolute path to videos month directory.
        """
        base_dir = CaptiXPaths.get_videos_dir()
        month_folder = CaptiXPaths.get_current_month_folder()
        return os.path.join(base_dir, month_folder)

    @staticmethod
    def ensure_directories() -> Tuple[str, str]:
        """Ensure default directories exist and return their paths.

        Creates the screenshots and videos directories if they don't exist.

        Returns:
            Tuple[str, str]: (screenshots_dir, videos_dir) absolute paths.
        """
        screenshots_dir = CaptiXPaths.get_screenshots_dir()
        videos_dir = CaptiXPaths.get_videos_dir()

        Path(screenshots_dir).mkdir(parents=True, exist_ok=True)
        Path(videos_dir).mkdir(parents=True, exist_ok=True)

        return screenshots_dir, videos_dir

    @staticmethod
    def generate_screenshot_filename(capture_type: str = "full") -> str:
        """Generate a timestamped screenshot filename.

        Args:
            capture_type: Type of capture (e.g., "full", "window", "area").
                         Defaults to "full".

        Returns:
            str: Filename in format: sc_YYYY-MM-DD_HHMMSS_<capture_type>.png

        Example:
            >>> CaptiXPaths.generate_screenshot_filename("window")
            'sc_2025-01-15_143022_window.png'
        """
        timestamp = datetime.now().strftime(CaptiXPaths.TIMESTAMP_FORMAT)
        return f"{CaptiXPaths.SCREENSHOT_PREFIX}_{timestamp}_{capture_type}{CaptiXPaths.SCREENSHOT_EXTENSION}"

    @staticmethod
    def get_screenshot_path(capture_type: str = "full", custom_dir: str = None) -> str:
        """Get full path for a new screenshot file.

        Args:
            capture_type: Type of capture (e.g., "full", "window", "area").
            custom_dir: Optional custom directory path. If None, uses default.

        Returns:
            str: Full absolute path to the screenshot file.
        """
        directory = custom_dir if custom_dir else CaptiXPaths.get_screenshots_dir()
        filename = CaptiXPaths.generate_screenshot_filename(capture_type)
        return os.path.join(directory, filename)
