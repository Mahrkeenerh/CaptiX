"""D-Bus service for video recording control.

Allows the recording to be stopped via D-Bus when the hotkey is pressed again.
Uses PyQt6's QtDBus for proper integration with Qt's event loop.
"""

import sys
from typing import Optional, Callable

try:
    from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusAbstractAdaptor
    from PyQt6.QtCore import QObject, pyqtSlot, pyqtClassInfo
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
    print("Warning: PyQt6 QtDBus not available, recording control disabled", file=sys.stderr)


if DBUS_AVAILABLE:
    @pyqtClassInfo("D-Bus Interface", "org.captix.VideoRecording")
    @pyqtClassInfo("D-Bus Introspection",
        '  <interface name="org.captix.VideoRecording">\n'
        '    <method name="StopRecording">\n'
        '      <arg direction="out" type="b" name="success"/>\n'
        '    </method>\n'
        '    <method name="IsRecording">\n'
        '      <arg direction="out" type="b" name="recording"/>\n'
        '    </method>\n'
        '  </interface>\n')
    class VideoRecordingAdaptor(QDBusAbstractAdaptor):
        """D-Bus adaptor for video recording control.

        This adaptor exposes methods on the D-Bus interface that can be called
        by external processes to control the recording.
        """

        def __init__(self, parent: QObject, stop_callback: Callable[[], None]):
            """Initialize the adaptor.

            Args:
                parent: Parent QObject
                stop_callback: Function to call when stop is requested
            """
            super().__init__(parent)
            self.stop_callback = stop_callback

        @pyqtSlot(result=bool)
        def StopRecording(self) -> bool:
            """D-Bus method to stop the recording.

            Returns:
                True if stop was triggered successfully
            """
            print("D-Bus: Stop recording requested")
            try:
                self.stop_callback()
                return True
            except Exception as e:
                print(f"Error stopping recording: {e}", file=sys.stderr)
                return False

        @pyqtSlot(result=bool)
        def IsRecording(self) -> bool:
            """D-Bus method to check if recording is active.

            Returns:
                True (always, since this service only exists during recording)
            """
            return True


class VideoRecordingService(QObject if DBUS_AVAILABLE else object):
    """D-Bus service for controlling active video recording.

    Registers on the session bus to allow external commands to stop the recording.
    Uses PyQt6's QtDBus for proper Qt event loop integration.
    """

    SERVICE_NAME = "org.captix.VideoRecording"
    OBJECT_PATH = "/org/captix/VideoRecording"
    INTERFACE_NAME = "org.captix.VideoRecording"

    def __init__(self, stop_callback: Callable[[], None]):
        """Initialize the recording service.

        Args:
            stop_callback: Function to call when stop is requested
        """
        if DBUS_AVAILABLE:
            super().__init__()

        self.stop_callback = stop_callback
        self._adaptor: Optional['VideoRecordingAdaptor'] = None
        self._registered = False

        if not DBUS_AVAILABLE:
            print("Warning: D-Bus not available, recording service disabled", file=sys.stderr)
            return

        try:
            # Get session bus connection
            bus = QDBusConnection.sessionBus()

            if not bus.isConnected():
                print("Warning: Could not connect to D-Bus session bus", file=sys.stderr)
                return

            # Register service name
            if not bus.registerService(self.SERVICE_NAME):
                print("Warning: Another recording is already active", file=sys.stderr)
                raise RuntimeError("Another recording is already active")

            # Create adaptor (this automatically handles D-Bus method calls)
            self._adaptor = VideoRecordingAdaptor(self, stop_callback)

            # Register object on the bus
            if not bus.registerObject(self.OBJECT_PATH, self):
                print("Warning: Failed to register D-Bus object", file=sys.stderr)
                bus.unregisterService(self.SERVICE_NAME)
                return

            self._registered = True
            print(f"Video recording service registered on D-Bus: {self.SERVICE_NAME}")

        except RuntimeError:
            raise
        except Exception as e:
            print(f"Warning: Failed to register recording service: {e}", file=sys.stderr)

    def release(self):
        """Release the D-Bus service."""
        if not DBUS_AVAILABLE or not self._registered:
            return

        try:
            bus = QDBusConnection.sessionBus()
            bus.unregisterObject(self.OBJECT_PATH)
            bus.unregisterService(self.SERVICE_NAME)
            self._registered = False
            print("Video recording service released")
        except Exception as e:
            print(f"Warning: Error releasing recording service: {e}", file=sys.stderr)

    def __del__(self):
        """Cleanup on destruction."""
        self.release()


def is_recording_active() -> bool:
    """Check if a video recording is currently active.

    Returns:
        True if recording service is registered on D-Bus
    """
    if not DBUS_AVAILABLE:
        return False

    try:
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False

        # Use the D-Bus daemon to check if the service name has an owner
        dbus_interface = QDBusInterface(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            bus
        )

        reply = dbus_interface.call("NameHasOwner", VideoRecordingService.SERVICE_NAME)

        # Check if the call succeeded and get the result
        if reply.type() == reply.MessageType.ReplyMessage:
            args = reply.arguments()
            if args:
                return bool(args[0])

        return False

    except Exception as e:
        print(f"Error checking recording status: {e}", file=sys.stderr)
        return False


def stop_active_recording() -> bool:
    """Stop the active recording via D-Bus.

    Returns:
        True if stop command was sent successfully
    """
    if not DBUS_AVAILABLE:
        print("Error: D-Bus not available", file=sys.stderr)
        return False

    try:
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            print("Error: Could not connect to D-Bus session bus", file=sys.stderr)
            return False

        # Get the recording service interface
        interface = QDBusInterface(
            VideoRecordingService.SERVICE_NAME,
            VideoRecordingService.OBJECT_PATH,
            VideoRecordingService.INTERFACE_NAME,
            bus
        )

        if not interface.isValid():
            print("Error: Recording service interface not valid", file=sys.stderr)
            return False

        # Call the StopRecording method
        reply = interface.call("StopRecording")

        # Check if the call succeeded
        if reply.type() == reply.MessageType.ReplyMessage:
            args = reply.arguments()
            if args:
                return bool(args[0])
            return True

        print(f"Error: D-Bus call failed: {reply.errorMessage()}", file=sys.stderr)
        return False

    except Exception as e:
        print(f"Error stopping recording: {e}", file=sys.stderr)
        return False
