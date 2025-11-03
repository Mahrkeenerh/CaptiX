"""Shared color palette for CaptiX UI.

This module provides a centralized color theme used across the application,
ensuring visual consistency and making theme modifications easier.
"""

from PyQt6.QtGui import QColor


class CaptiXColors:
    """Centralized color palette for CaptiX UI components.

    All UI colors should be defined here to maintain consistency and
    enable easy theme modifications in the future.
    """

    # Primary theme color - used for highlights, borders, and interactive elements
    THEME_BLUE = QColor(0, 150, 255, 200)  # Semi-transparent blue
    THEME_BLUE_SOLID = QColor(0, 150, 255, 255)  # Fully opaque blue (magnifier)

    # Overlay colors - used for the dark background overlay
    DARK_OVERLAY_BLACK = QColor(0, 0, 0)  # Alpha channel set dynamically

    # Text colors
    WHITE_TEXT = QColor(255, 255, 255, 255)  # Fully opaque white
    WHITE_TEXT_READABLE = QColor(255, 255, 255, 220)  # Slightly transparent for better readability

    # Background colors
    SEMI_TRANSPARENT_BLACK = QColor(0, 0, 0, 120)  # For text backgrounds
    DARK_BACKGROUND = QColor(40, 40, 40, 240)  # For magnifier background

    # Grid and guide colors (magnifier)
    SUBTLE_WHITE_GRID = QColor(255, 255, 255, 60)  # Grid lines
    SUBTLE_WHITE_GUIDE = QColor(255, 255, 255, 50)  # Crosshair guides
    WHITE_BORDER = QColor(255, 255, 255, 180)  # Magnifier border
