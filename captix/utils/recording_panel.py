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

        # Position and size
        self.setGeometry(x, y, width, height)

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

    def paintEvent(self, event):
        """Draw red border around recording area."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Red semi-transparent border (3px thick)
        pen = QPen(QColor(255, 0, 0, 200), 3, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Draw rectangle border (inset slightly to ensure visibility)
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
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )

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
        self.pulse_state = not self.pulse_state

        if self.pulse_state:
            self.indicator_label.setStyleSheet("color: red; font-size: 20px; font-weight: bold;")
        else:
            self.indicator_label.setStyleSheet("color: #ffcccc; font-size: 20px; font-weight: bold;")

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
