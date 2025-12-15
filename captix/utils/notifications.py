"""
Desktop notification system for CaptiX.

This module handles desktop notifications for screenshots and recordings,
including:
- Desktop notifications via notify-send or DBus
- Sound playback on screenshot/recording completion
- Clickable notifications that open the containing folder
- File size and duration reporting
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class NotificationTimeouts:
    """Timeout constants for notifications.

    These values control how long notifications stay visible on the desktop
    and how long to wait for notification system responses.
    """

    # Standard notification display durations (milliseconds)
    NOTIFICATION_DISPLAY_MS = 5000  # How long to show notifications (5 seconds)
    GLIB_LOOP_TIMEOUT_MS = 6000  # GLib event loop timeout (6 seconds)
    ERROR_NOTIFICATION_MS = 3000  # Shorter timeout for errors (3 seconds)


class NotificationSystem:
    """Handles desktop notifications for CaptiX."""

    def __init__(self):
        """Initialize the notification system."""
        self.notification_available = self._check_notification_support()
        self.sound_available = self._check_sound_support()

    def _check_notification_support(self) -> bool:
        # Try notify-send first (most common)
        try:
            result = subprocess.run(
                ["which", "notify-send"],
                capture_output=True,
                timeout=2,
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"Failed to check for notify-send: {e}")
            return False

    def _check_sound_support(self) -> bool:
        # Check for paplay (PulseAudio)
        try:
            result = subprocess.run(
                ["which", "paplay"],
                capture_output=True,
                timeout=2,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

        # Check for aplay (ALSA)
        try:
            result = subprocess.run(
                ["which", "aplay"],
                capture_output=True,
                timeout=2,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

        logger.warning("No sound playback system found (paplay or aplay)")
        return False

    def _play_sound(self, sound_name: str = "camera-shutter") -> None:
        """
        Play a system sound for screenshot feedback.

        Args:
            sound_name: The name of the sound to play (freedesktop sound theme)
        """
        if not self.sound_available:
            return

        # Try paplay first (PulseAudio/PipeWire)
        try:
            # First try using the system sound theme
            subprocess.Popen(
                ["paplay", f"/usr/share/sounds/freedesktop/stereo/{sound_name}.oga"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass

        # Try canberra-gtk-play (recommended for freedesktop themes)
        try:
            subprocess.Popen(
                ["canberra-gtk-play", "-i", sound_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass

        # Fallback to generic beep sound
        try:
            subprocess.Popen(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            logger.debug("Could not play screenshot sound")

    def _show_dbus_notification_with_action(
        self,
        summary: str,
        body: str,
        icon: str,
        folder_path: str,
    ) -> None:
        """
        Show a notification with clickable action using GObject Notify.

        Args:
            summary: Notification title
            body: Notification body text
            icon: Icon name
            folder_path: Path to open when clicked
        """
        try:
            # Run notification in a subprocess with python -c
            # This is the most reliable way to handle GLib.MainLoop
            code = f"""
import subprocess
from gi import require_version
require_version('Notify', '0.7')
from gi.repository import Notify, GLib

def on_action(notification, action):
    subprocess.run(['xdg-open', '{folder_path}'], check=False)

Notify.init('CaptiX')
notification = Notify.Notification.new('{summary}', '''{body}''', '{icon}')
notification.set_timeout({NotificationTimeouts.NOTIFICATION_DISPLAY_MS})
notification.add_action('default', 'Open Folder', on_action)
notification.show()

loop = GLib.MainLoop()
GLib.timeout_add({NotificationTimeouts.GLIB_LOOP_TIMEOUT_MS}, loop.quit)
loop.run()
"""
            subprocess.Popen(
                ["python3", "-c", code],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        except Exception as e:
            logger.warning(f"GObject notification failed, falling back to simple notify-send: {e}")
            # Fallback to simple notification
            subprocess.run(
                [
                    "notify-send",
                    "-i", icon,
                    "-u", "normal",
                    "-t", str(NotificationTimeouts.NOTIFICATION_DISPLAY_MS),
                    "-a", "CaptiX",
                    summary,
                    body,
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def _format_file_size(self, size_bytes: int) -> str:
        """
        Format file size in human-readable format.

        Args:
            size_bytes: File size in bytes

        Returns:
            Formatted string (e.g., "2.4 MB", "156 KB")
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def notify_screenshot_saved(
        self,
        filepath: str,
        file_size: int,
        play_sound: bool = True,
    ) -> None:
        """
        Show a notification that a screenshot was saved.

        Args:
            filepath: Full path to the saved screenshot
            file_size: Size of the file in bytes
            play_sound: Whether to play a sound with the notification
        """
        if not self.notification_available:
            logger.warning("Notification system not available")
            return

        # Play sound effect
        if play_sound:
            self._play_sound("camera-shutter")

        # Format the file size
        size_str = self._format_file_size(file_size)

        # Get the directory containing the screenshot
        file_path_obj = Path(filepath)
        directory = str(file_path_obj.parent)
        filename = file_path_obj.name

        # Create notification body
        body = f"{size_str}\n{filename}"

        try:
            # Use D-Bus directly for clickable notification
            # This works even with older notify-send versions
            self._show_dbus_notification_with_action(
                "CaptiX - Screenshot Saved!",
                f"{size_str}\n{filepath}",
                "camera-photo",
                directory
            )
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")

    def notify_recording_saved(
        self,
        filepath: str,
        file_size: int,
        duration: str,
        play_sound: bool = True,
    ) -> None:
        """
        Show a notification that a recording was saved.

        Args:
            filepath: Full path to the saved recording
            file_size: Size of the file in bytes
            duration: Duration string (e.g., "2:47")
            play_sound: Whether to play a sound with the notification
        """
        if not self.notification_available:
            logger.warning("Notification system not available")
            return

        # Play sound effect
        if play_sound:
            self._play_sound("camera-shutter")

        # Format the file size
        size_str = self._format_file_size(file_size)

        # Get the directory containing the recording
        file_path_obj = Path(filepath)
        directory = str(file_path_obj.parent)
        filename = file_path_obj.name

        try:
            # Use D-Bus directly for clickable notification
            self._show_dbus_notification_with_action(
                "CaptiX - Recording Saved!",
                f"Duration: {duration} | {size_str}\n{filepath}",
                "media-record",
                directory
            )
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")

    def notify_recording_aborted(self) -> None:
        """Show a notification that recording was aborted."""
        if not self.notification_available:
            return

        try:
            subprocess.Popen(
                [
                    "notify-send",
                    "-i", "dialog-warning",
                    "-u", "normal",
                    "-t", str(NotificationTimeouts.ERROR_NOTIFICATION_MS),
                    "-a", "CaptiX",
                    "CaptiX - Recording Aborted",
                    "Recording was cancelled",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")

    def notify_error(self, title: str, message: str) -> None:
        """
        Show an error notification.

        Args:
            title: Error title
            message: Error message
        """
        if not self.notification_available:
            return

        try:
            subprocess.Popen(
                [
                    "notify-send",
                    "-i", "dialog-error",
                    "-u", "critical",
                    "-t", str(NotificationTimeouts.NOTIFICATION_DISPLAY_MS),
                    "-a", "CaptiX",
                    f"CaptiX - {title}",
                    message,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.error(f"Failed to show error notification: {e}")


# Global notification system instance
_notification_system: Optional[NotificationSystem] = None


def get_notification_system() -> NotificationSystem:
    """Get the global notification system instance."""
    global _notification_system
    if _notification_system is None:
        _notification_system = NotificationSystem()
    return _notification_system


# Convenience functions for common operations
def notify_screenshot_saved(filepath: str, file_size: int, play_sound: bool = True) -> None:
    """Show notification for saved screenshot."""
    get_notification_system().notify_screenshot_saved(filepath, file_size, play_sound)


def notify_recording_saved(filepath: str, file_size: int, duration: str, play_sound: bool = True) -> None:
    """Show notification for saved recording."""
    get_notification_system().notify_recording_saved(filepath, file_size, duration, play_sound)


def notify_recording_aborted() -> None:
    """Show notification for aborted recording."""
    get_notification_system().notify_recording_aborted()


def notify_error(title: str, message: str) -> None:
    """Show error notification."""
    get_notification_system().notify_error(title, message)


def send_notification(title: str, message: str, urgency: str = "normal", icon: str = "dialog-information") -> None:
    """
    Send a generic desktop notification.

    Args:
        title: Notification title
        message: Notification message body
        urgency: Urgency level ("low", "normal", or "critical")
        icon: Icon name to display
    """
    notification_system = get_notification_system()
    if not notification_system.notification_available:
        logger.warning(f"Notification not available: {title} - {message}")
        return

    try:
        subprocess.Popen(
            [
                "notify-send",
                "-i", icon,
                "-u", urgency,
                "-t", str(NotificationTimeouts.NOTIFICATION_DISPLAY_MS),
                "-a", "CaptiX",
                f"CaptiX - {title}",
                message,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
