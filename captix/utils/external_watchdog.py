"""
External watchdog process that monitors CaptiX screenshot UI.

This watchdog runs as a separate process and monitors the screenshot UI.
If the UI becomes unresponsive (event loop frozen), the watchdog will
kill it after the timeout expires.

This is the ONLY failsafe that works when the Qt event loop is completely frozen.
"""

import os
import sys
import time
import signal
import subprocess
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class ExternalWatchdog:
    """
    External watchdog that monitors a process and kills it if it becomes unresponsive.

    This watchdog runs as a completely separate process and uses a heartbeat file
    to detect if the monitored process is still responsive.
    """

    def __init__(self, timeout_seconds: int = 60):
        """
        Initialize the external watchdog.

        Args:
            timeout_seconds: How long to wait before killing the process
        """
        self.timeout_seconds = timeout_seconds
        self.heartbeat_file = Path(f"/tmp/captix_heartbeat_{os.getpid()}")
        self.watchdog_pid = None

    def update_heartbeat(self):
        """Update the heartbeat file to signal the watchdog we're still alive."""
        try:
            self.heartbeat_file.write_text(str(time.time()))
        except (OSError, IOError) as e:
            logger.warning(f"Failed to update heartbeat file {self.heartbeat_file}: {e}")

    def start_watchdog(self, pid_to_monitor: int):
        """
        Start the external watchdog process.

        Args:
            pid_to_monitor: PID of the process to monitor
        """
        # Create initial heartbeat
        self.update_heartbeat()

        # Prepare configuration as JSON (safe from injection)
        config = {
            'heartbeat_file': str(self.heartbeat_file),
            'pid_to_monitor': pid_to_monitor,
            'timeout_seconds': self.timeout_seconds
        }

        # Watchdog code that receives config via JSON
        # This eliminates string interpolation injection risks
        watchdog_code = '''
import os
import sys
import time
import signal
import json
from pathlib import Path

# Parse configuration from JSON argument (safe from injection)
config = json.loads(sys.argv[1])
heartbeat_file = Path(config['heartbeat_file'])
pid_to_monitor = config['pid_to_monitor']
timeout_seconds = config['timeout_seconds']

print(f"[Watchdog] Monitoring PID {pid_to_monitor} with {timeout_seconds}s timeout", flush=True)

while True:
    time.sleep(1)

    # Check if process still exists
    try:
        os.kill(pid_to_monitor, 0)
    except OSError:
        print(f"[Watchdog] Process {pid_to_monitor} no longer exists - exiting watchdog", flush=True)
        heartbeat_file.unlink(missing_ok=True)
        sys.exit(0)

    # Check heartbeat
    if heartbeat_file.exists():
        try:
            last_heartbeat = float(heartbeat_file.read_text())
            elapsed = time.time() - last_heartbeat

            if elapsed > timeout_seconds:
                print(f"[Watchdog] TIMEOUT! No heartbeat for {elapsed:.1f}s - killing process {pid_to_monitor}", flush=True)

                # Send notification before killing
                try:
                    import subprocess
                    subprocess.run([
                        "notify-send",
                        "-i", "dialog-warning",
                        "-u", "critical",
                        "-t", "5000",
                        "-a", "CaptiX",
                        "CaptiX Watchdog",
                        f"Screenshot overlay frozen for {int(elapsed)}s - force killing"
                    ], check=False, timeout=2)
                except:
                    pass

                # Kill the process
                os.kill(pid_to_monitor, signal.SIGKILL)
                heartbeat_file.unlink(missing_ok=True)
                print(f"[Watchdog] Process killed successfully", flush=True)
                sys.exit(0)
        except Exception as e:
            print(f"[Watchdog] Error checking heartbeat: {e}", flush=True)
    else:
        print(f"[Watchdog] Heartbeat file disappeared - exiting watchdog", flush=True)
        sys.exit(0)
'''

        try:
            # Start watchdog as a detached subprocess with JSON config
            process = subprocess.Popen(
                [sys.executable, "-c", watchdog_code, json.dumps(config)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent
            )
            self.watchdog_pid = process.pid
            logger.info(f"External watchdog started (PID: {self.watchdog_pid}, timeout: {self.timeout_seconds}s)")
        except Exception as e:
            logger.error(f"Failed to start external watchdog: {e}")

    def stop_watchdog(self):
        """Stop the external watchdog process."""
        # Delete heartbeat file to signal watchdog to exit
        try:
            self.heartbeat_file.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Failed to remove heartbeat file: {e}")

        # Try to kill watchdog process if it's still running
        if self.watchdog_pid:
            try:
                os.kill(self.watchdog_pid, signal.SIGTERM)
                logger.info(f"External watchdog stopped (PID: {self.watchdog_pid})")
            except ProcessLookupError:
                pass  # Already dead
            except Exception as e:
                logger.warning(f"Failed to stop watchdog: {e}")
