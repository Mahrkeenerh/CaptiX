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

    def update_heartbeat(self) -> None:
        try:
            self.heartbeat_file.write_text(str(time.time()))
        except (OSError, IOError) as e:
            logger.warning(f"Failed to update heartbeat file {self.heartbeat_file}: {e}")

    def start_watchdog(self, pid_to_monitor: int) -> None:
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
import subprocess
import logging
from pathlib import Path
from datetime import datetime

# Setup logging to file for debugging
log_file = Path("/tmp/captix_watchdog.log")
logging.basicConfig(
    filename=str(log_file),
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger()

def log_and_print(msg, level='INFO'):
    """Log to both file and stdout for debugging"""
    print(f"[Watchdog] {msg}", flush=True)
    getattr(logger, level.lower())(msg)

# Parse configuration from JSON argument (safe from injection)
config = json.loads(sys.argv[1])
heartbeat_file = Path(config['heartbeat_file'])
pid_to_monitor = config['pid_to_monitor']
timeout_seconds = config['timeout_seconds']

# Flag to track if we've already killed the process
kill_executed = False

def alarm_handler(signum, frame):
    """
    LAST RESORT failsafe handler - executes if we get stuck in notification code.
    This runs when SIGALRM fires, guaranteeing kill even if notification hangs.
    """
    global kill_executed
    if not kill_executed:
        log_and_print("ALARM FIRED! Force killing process immediately (notification may have hung)", 'CRITICAL')
        try:
            os.kill(pid_to_monitor, signal.SIGKILL)
            kill_executed = True
            log_and_print(f"Process {pid_to_monitor} killed via alarm handler", 'CRITICAL')
        except Exception as e:
            log_and_print(f"Alarm handler kill failed: {e}", 'ERROR')
    heartbeat_file.unlink(missing_ok=True)
    sys.exit(0)

# Install alarm signal handler as ultimate failsafe
signal.signal(signal.SIGALRM, alarm_handler)

log_and_print(f"Monitoring PID {pid_to_monitor} with {timeout_seconds}s timeout")
log_and_print(f"Heartbeat file: {heartbeat_file}")
log_and_print(f"Log file: {log_file}")

while True:
    time.sleep(1)

    # Check if process still exists
    try:
        os.kill(pid_to_monitor, 0)
    except OSError:
        log_and_print(f"Process {pid_to_monitor} no longer exists - exiting watchdog")
        heartbeat_file.unlink(missing_ok=True)
        sys.exit(0)

    # Check heartbeat
    if heartbeat_file.exists():
        try:
            last_heartbeat = float(heartbeat_file.read_text())
            elapsed = time.time() - last_heartbeat

            if elapsed > timeout_seconds:
                log_and_print(f"TIMEOUT DETECTED! No heartbeat for {elapsed:.1f}s", 'WARNING')
                log_and_print(f"Initiating kill sequence for process {pid_to_monitor}", 'CRITICAL')

                # Set 1-second alarm as ultimate failsafe
                # If anything below hangs, alarm handler will kill the process
                log_and_print("Setting 1-second alarm failsafe", 'INFO')
                signal.alarm(1)

                # Try to send notification (fire-and-forget with Popen)
                # Don't wait for it to complete - we need to kill immediately
                # NOTE: Using 'normal' urgency instead of 'critical' to allow auto-dismiss.
                # Many notification daemons ignore timeout for critical notifications.
                log_and_print("Attempting to send notification (fire-and-forget)", 'INFO')
                try:
                    subprocess.Popen(
                        [
                            "notify-send",
                            "-i", "dialog-warning",
                            "-u", "normal",
                            "-t", "5000",
                            "-a", "CaptiX",
                            "CaptiX Watchdog",
                            f"Screenshot overlay frozen for {int(elapsed)}s - force killing"
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True  # Fully detach notification process
                    )
                    log_and_print("Notification process spawned (not waiting for completion)", 'INFO')
                except Exception as e:
                    log_and_print(f"Notification spawn failed (non-critical): {e}", 'WARNING')

                # Cancel alarm if we got here quickly (notification didn't hang)
                signal.alarm(0)
                log_and_print("Alarm cancelled - proceeding to kill", 'INFO')

                # KILL THE PROCESS IMMEDIATELY
                if not kill_executed:
                    log_and_print(f"Sending SIGKILL to process {pid_to_monitor}", 'CRITICAL')
                    try:
                        os.kill(pid_to_monitor, signal.SIGKILL)
                        kill_executed = True
                        log_and_print("SIGKILL sent successfully", 'CRITICAL')
                    except Exception as e:
                        log_and_print(f"SIGKILL failed: {e}", 'ERROR')

                # Clean up
                heartbeat_file.unlink(missing_ok=True)
                log_and_print("Heartbeat file removed", 'INFO')
                log_and_print("Watchdog job complete - exiting", 'INFO')
                sys.exit(0)
        except Exception as e:
            log_and_print(f"Error checking heartbeat: {e}", 'ERROR')
    else:
        log_and_print("Heartbeat file disappeared - exiting watchdog")
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

    def stop_watchdog(self) -> None:
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
