"""Single instance management using D-Bus.

This module ensures only one instance of the screenshot UI can run at a time.
Uses D-Bus session bus to register a unique service name.
"""

import sys
from typing import Optional

try:
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
    print("Warning: D-Bus not available, single-instance control disabled", file=sys.stderr)


class SingleInstanceManager:
    """Manages single instance constraint using D-Bus service registration.

    Registers a unique D-Bus service name on the session bus. If the name is
    already taken, it means another instance is running.
    """

    SERVICE_NAME = "org.captix.ScreenshotUI"

    def __init__(self):
        """Initialize the single instance manager."""
        self.bus: Optional[dbus.Bus] = None
        self.name: Optional[dbus.service.BusName] = None

    def acquire(self) -> bool:
        """Attempt to acquire single instance lock.

        Returns:
            True if this is the first/only instance (lock acquired)
            False if another instance is already running
        """
        if not DBUS_AVAILABLE:
            # D-Bus not available - allow launch but log warning
            print("Warning: D-Bus unavailable, allowing launch without instance check",
                  file=sys.stderr)
            return True

        try:
            # Initialize D-Bus main loop (required for service registration)
            DBusGMainLoop(set_as_default=True)

            # Connect to session bus
            self.bus = dbus.SessionBus()

            # Try to register our service name
            # do_not_queue=True means fail immediately if name exists
            self.name = dbus.service.BusName(
                self.SERVICE_NAME,
                bus=self.bus,
                do_not_queue=True
            )

            # Successfully acquired the name - we are the first instance
            return True

        except dbus.exceptions.NameExistsException:
            # Another instance already owns this name
            return False

        except Exception as e:
            # Unexpected error - log but allow launch to avoid breaking functionality
            print(f"Warning: D-Bus error during instance check: {e}", file=sys.stderr)
            print("Allowing launch without instance check", file=sys.stderr)
            return True

    def release(self):
        """Release the D-Bus service name.

        Called automatically when the object is destroyed or process exits.
        Explicit release is optional.
        """
        if self.name is not None:
            try:
                del self.name
                self.name = None
            except Exception as e:
                print(f"Warning: Error releasing D-Bus name: {e}", file=sys.stderr)

    def __del__(self):
        """Cleanup on destruction."""
        self.release()
