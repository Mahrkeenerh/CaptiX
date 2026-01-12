"""Recording control panel and area border indicator.

Provides a floating control panel with system tray integration for managing
active video recordings.
"""

import time
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QIcon, QPixmap
from Xlib import display as xlib_display, X
from Xlib.ext import shape
import logging

logger = logging.getLogger(__name__)


class RecordingAreaBorder(QWidget):
    """Static red border overlay indicating recording area.

    Shows a semi-transparent red border around the recording area
    for non-fullscreen recordings. The border stays in place even
    if the window moves.
    """

    def __init__(self, x: int, y: int, width: int, height: int):
        """Initialize recording area border.

        Args:
            x, y: Top-left corner of recording area
            width, height: Recording area dimensions
        """
        super().__init__()

        # Border thickness + padding to keep it outside recording area
        border_offset = 5

        # Position and size - OUTSIDE the recording area
        self.setGeometry(
            x - border_offset,
            y - border_offset,
            width + (border_offset * 2),
            height + (border_offset * 2)
        )

        # Window flags for transparent overlay
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.X11BypassWindowManagerHint
        )

        # Transparent background
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        logger.info(f"Created recording border: {width}x{height} at ({x},{y})")

    def showEvent(self, event):
        """Apply X11 input shape after window is shown."""
        super().showEvent(event)
        # Use X11 SHAPE extension to make window click-through
        try:
            d = xlib_display.Display()
            win = d.create_resource_object('window', int(self.winId()))
            win.shape_rectangles(
                shape.SO.Set,
                shape.SK.Input,
                X.Unsorted,
                0, 0,
                []  # Empty = fully click-through
            )
            d.sync()
            logger.info("Recording border: X11 input shape set to empty")
        except Exception as e:
            logger.warning(f"Failed to set X11 input shape on border: {e}")

    def paintEvent(self, event):
        """Draw red border around recording area."""
        painter = QPainter(self)

        pen = QPen(QColor(255, 0, 0, 200), 3, Qt.PenStyle.DashDotLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Inset to keep border outside recording area (offset=5, pen=3, so inset by 2)
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.drawRect(rect)


class RecordingControlPanel(QWidget):
    """Floating control panel for managing video recording.

    Displays recording status, timer, file size, and provides
    stop/abort buttons. Integrates with system tray.
    """

    # Signals
    stop_requested = pyqtSignal()
    abort_requested = pyqtSignal()

    def __init__(self, recorder, recording_area: tuple, is_fullscreen: bool = False):
        """Initialize recording control panel.

        Args:
            recorder: Video recorder instance (FFmpegRecorder or XCompositeRecorder)
            recording_area: Tuple of (x, y, width, height)
            is_fullscreen: Whether recording full screen
        """
        super().__init__()

        self.recorder = recorder
        self.recording_area = recording_area
        self.is_fullscreen = is_fullscreen

        # Window configuration
        self.setWindowTitle("CaptiX Recording")
        # Don't use Tool flag - it prevents the window from keeping the app alive
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)

        # Setup UI
        self._setup_ui()

        # Setup system tray
        self._setup_system_tray()

        # Setup update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_display)
        self.update_timer.start(1000)  # Update every second

        # Pulse animation for recording indicator
        self.pulse_state = True
        self.pulse_timer = QTimer()
        self.pulse_timer.timeout.connect(self._pulse_indicator)
        self.pulse_timer.start(500)  # Pulse every 500ms

        # Error state
        self._error_detected = False

        logger.info("Recording control panel initialized")

    def _setup_ui(self):
        """Setup user interface components."""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Top row: Recording indicator + Timer + File size
        top_layout = QHBoxLayout()

        # Recording indicator (pulsing red dot)
        self.indicator_label = QLabel("●")
        self.indicator_label.setStyleSheet("color: red; font-size: 20px; font-weight: bold;")
        top_layout.addWidget(self.indicator_label)

        # "REC" label
        rec_label = QLabel("REC")
        rec_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        top_layout.addWidget(rec_label)

        top_layout.addSpacing(20)

        # Timer
        self.timer_label = QLabel("00:00:00")
        self.timer_label.setStyleSheet("font-size: 14px; font-family: monospace;")
        top_layout.addWidget(self.timer_label)

        top_layout.addSpacing(20)

        # File size
        self.filesize_label = QLabel("~0 MB")
        self.filesize_label.setStyleSheet("font-size: 14px; color: #666;")
        top_layout.addWidget(self.filesize_label)

        top_layout.addStretch()
        layout.addLayout(top_layout)

        # Recording area info
        width, height = self.recording_area[2], self.recording_area[3]
        area_type = "Full Screen" if self.is_fullscreen else "Custom Area"
        self.area_label = QLabel(f"Recording: {width}×{height} ({area_type})")
        self.area_label.setStyleSheet("font-size: 12px; color: #888;")
        layout.addWidget(self.area_label)

        # Button row
        button_layout = QHBoxLayout()

        # Stop button
        self.stop_button = QPushButton("■ Stop")
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 20px;
                font-size: 13px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        button_layout.addWidget(self.stop_button)

        # Abort button
        self.abort_button = QPushButton("✕ Abort")
        self.abort_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 8px 20px;
                font-size: 13px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.abort_button.clicked.connect(self._on_abort_clicked)
        button_layout.addWidget(self.abort_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Set minimum size
        self.setMinimumWidth(400)

    def _setup_system_tray(self):
        """Setup system tray icon."""
        # Create icon (red dot)
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(255, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(6, 6, 20, 20)
        painter.end()

        icon = QIcon(pixmap)

        # Create system tray icon
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("CaptiX - Recording in progress")

        # Create context menu
        tray_menu = QMenu()

        show_action = tray_menu.addAction("Show Control Panel")
        show_action.triggered.connect(self.show)

        tray_menu.addSeparator()

        stop_action = tray_menu.addAction("■ Stop Recording")
        stop_action.triggered.connect(self._on_stop_clicked)

        abort_action = tray_menu.addAction("✕ Abort Recording")
        abort_action.triggered.connect(self._on_abort_clicked)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        logger.info("System tray icon created")

    def _update_display(self):
        """Update timer and file size display."""
        # Check for FFmpeg errors first
        if not self._error_detected and hasattr(self.recorder, 'get_error'):
            error = self.recorder.get_error()
            if error:
                self._show_error_state(error)
                return

        # Update timer
        duration = self.recorder.get_duration()
        self.timer_label.setText(self._format_duration(duration))

        # Update file size
        file_size = self.recorder.get_file_size()
        self.filesize_label.setText(f"~{self._format_file_size(file_size)}")

        # Update tray tooltip
        self.tray_icon.setToolTip(
            f"CaptiX Recording - {self._format_duration(duration)} - {self._format_file_size(file_size)}"
        )

    def _pulse_indicator(self):
        """Pulse recording indicator."""
        if self._error_detected:
            return  # Don't pulse when in error state

        self.pulse_state = not self.pulse_state

        if self.pulse_state:
            self.indicator_label.setStyleSheet("color: red; font-size: 20px; font-weight: bold;")
        else:
            self.indicator_label.setStyleSheet("color: #ffcccc; font-size: 20px; font-weight: bold;")

    def _show_error_state(self, error_message: str):
        """Show error state in the UI when FFmpeg fails.

        Args:
            error_message: Error message from FFmpeg
        """
        self._error_detected = True
        logger.error(f"Recording failed: {error_message}")

        # Stop pulse animation
        self.pulse_timer.stop()

        # Update indicator to show error
        self.indicator_label.setText("!")
        self.indicator_label.setStyleSheet("color: #ff6600; font-size: 20px; font-weight: bold;")

        # Update timer label to show error
        self.timer_label.setText("ERROR")
        self.timer_label.setStyleSheet("font-size: 14px; font-family: monospace; color: #ff6600;")

        # Show error in area label
        # Truncate long error messages
        short_error = error_message[:80] + "..." if len(error_message) > 80 else error_message
        self.area_label.setText(f"Recording failed: {short_error}")
        self.area_label.setStyleSheet("font-size: 12px; color: #ff6600;")

        # Update tray
        self.tray_icon.setToolTip(f"CaptiX - Recording failed: {short_error}")

        # Change stop button to "Close"
        self.stop_button.setText("Close")
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #666666;
                color: white;
                border: none;
                padding: 8px 20px;
                font-size: 13px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #555555;
            }
        """)

        # Hide abort button (nothing to abort)
        self.abort_button.hide()

    def _format_duration(self, seconds: float) -> str:
        """Format duration as HH:MM:SS.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format.

        Args:
            size_bytes: File size in bytes

        Returns:
            Formatted file size string
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def _on_stop_clicked(self):
        """Handle stop button click."""
        self.stop_button.setEnabled(False)
        self.abort_button.setEnabled(False)
        self.timer_label.setText("Stopping...")

        # Stop timers
        self.update_timer.stop()
        self.pulse_timer.stop()

        logger.info("Stop button clicked")
        self.stop_requested.emit()

    def _on_abort_clicked(self):
        """Handle abort button click."""
        self.stop_button.setEnabled(False)
        self.abort_button.setEnabled(False)
        self.timer_label.setText("Aborting...")

        # Stop timers
        self.update_timer.stop()
        self.pulse_timer.stop()

        logger.info("Abort button clicked")
        self.abort_requested.emit()

    def closeEvent(self, event):
        """Handle window close event."""
        # Hide tray icon when closing
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()

        # Stop timers
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        if hasattr(self, 'pulse_timer'):
            self.pulse_timer.stop()

        event.accept()
