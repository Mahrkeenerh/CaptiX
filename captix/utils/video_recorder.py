"""Video recording with FFmpeg and XComposite window tracking.

Provides two recording modes:
1. FFmpegRecorder - Static area recording (fullscreen, custom area, static window)
2. XCompositeRecorder - Window tracking recording (follows window movement)
"""

import subprocess
import threading
import time
import os
import logging
from typing import Optional, Tuple
from enum import Enum
from pathlib import Path

from .audio_detect import AudioSystem
from .capture import ScreenCapture
from .window_detect import WindowDetector

logger = logging.getLogger(__name__)


class RecordingState(Enum):
    """Recording state machine."""
    IDLE = "idle"
    RECORDING = "recording"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class FFmpegRecorder:
    """FFmpeg-based video recorder for static screen areas.

    Uses FFmpeg's x11grab to record a fixed screen region.
    Supports fullscreen, custom area, and static window recording.
    """

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.output_file: Optional[str] = None
        self.recording_area: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)
        self.start_time: Optional[float] = None
        self.state = RecordingState.IDLE
        self.audio_system = AudioSystem()
        self.capture = ScreenCapture()
        self._hw_encoder = self._detect_hw_encoder()
        self._stderr_output: str = ""
        self._process_error: Optional[str] = None

    def _detect_hw_encoder(self) -> Optional[str]:
        """Detect available hardware encoder.

        Returns:
            Encoder name ('h264_nvenc', 'h264_vaapi', 'h264_qsv') or None for software
        """
        # Check for NVENC (NVIDIA)
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True, text=True, timeout=5
            )
            if 'h264_nvenc' in result.stdout:
                # Verify NVENC actually works (need 256x256 minimum for NVENC)
                test = subprocess.run(
                    ['ffmpeg', '-hide_banner', '-f', 'lavfi', '-i', 'color=c=black:s=256x256:d=0.1',
                     '-c:v', 'h264_nvenc', '-f', 'null', '-'],
                    capture_output=True, timeout=5
                )
                if test.returncode == 0:
                    logger.info("Using NVIDIA NVENC hardware encoder")
                    return 'h264_nvenc'
        except Exception as e:
            logger.debug(f"NVENC check failed: {e}")

        # Check for VAAPI (Intel/AMD)
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True, text=True, timeout=5
            )
            if 'h264_vaapi' in result.stdout:
                logger.info("Using VAAPI hardware encoder")
                return 'h264_vaapi'
        except Exception:
            pass

        logger.info("Using software encoder (libx264)")
        return None

    def start_fullscreen(self, output_file: str, fps: int = 30, include_mic: bool = False) -> bool:
        """Start recording full screen.

        Args:
            output_file: Path to output video file
            fps: Frames per second
            include_mic: Include microphone input

        Returns:
            True if recording started successfully
        """
        # Get screen geometry
        geom = self.capture.get_screen_geometry()
        return self.start_area(geom[0], geom[1], geom[2], geom[3], output_file, fps, include_mic)

    def start_area(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        output_file: str,
        fps: int = 30,
        include_mic: bool = False
    ) -> bool:
        """Start recording custom screen area.

        Args:
            x, y: Top-left corner coordinates
            width, height: Area dimensions
            output_file: Path to output video file
            fps: Frames per second
            include_mic: Include microphone input

        Returns:
            True if recording started successfully
        """
        if self.state != RecordingState.IDLE:
            logger.error(f"Cannot start recording in state: {self.state}")
            return False

        # Validate area
        if width <= 0 or height <= 0:
            logger.error(f"Invalid recording area: {width}x{height}")
            return False

        # Clip to screen bounds (FFmpeg fails if capture area extends beyond screen)
        screen_geom = self.capture.get_screen_geometry()
        screen_width, screen_height = screen_geom[2], screen_geom[3]

        # Ensure x, y are within screen
        x = max(0, min(x, screen_width - 1))
        y = max(0, min(y, screen_height - 1))

        # Clip width/height to not exceed screen boundaries
        if x + width > screen_width:
            width = screen_width - x
            logger.debug(f"Clipped width to {width} to fit screen")
        if y + height > screen_height:
            height = screen_height - y
            logger.debug(f"Clipped height to {height} to fit screen")

        # Ensure even dimensions (required by most codecs)
        width = width - (width % 2)
        height = height - (height % 2)

        # Final validation after clipping
        if width <= 0 or height <= 0:
            logger.error(f"Recording area too small after clipping: {width}x{height}")
            return False

        # Build FFmpeg command
        cmd = self._build_ffmpeg_command(x, y, width, height, output_file, fps, include_mic)

        try:
            # Start FFmpeg process with stderr capture
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )

            self.output_file = output_file
            self.recording_area = (x, y, width, height)
            self.start_time = time.time()
            self.state = RecordingState.RECORDING
            self._stderr_output = ""
            self._process_error = None

            # Start stderr reader thread
            self._stderr_thread = threading.Thread(
                target=self._read_stderr,
                daemon=True
            )
            self._stderr_thread.start()

            logger.info(f"Started recording: {width}x{height} at ({x},{y}) -> {output_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to start FFmpeg: {e}")
            self.state = RecordingState.ERROR
            return False

    def start_window(
        self,
        window_id: int,
        output_file: str,
        fps: int = 30,
        include_mic: bool = False
    ) -> bool:
        """Start recording window (static position).

        Window content will be recorded, but the recording area is fixed.
        If the window moves, the recording area stays in place.

        Args:
            window_id: X11 window ID
            output_file: Path to output video file
            fps: Frames per second
            include_mic: Include microphone input

        Returns:
            True if recording started successfully
        """
        # Get window geometry
        window_detector = WindowDetector()
        windows = window_detector.get_visible_windows()

        window_info = None
        for win in windows:
            if win.window_id == window_id:
                window_info = win
                break

        if not window_info:
            logger.error(f"Window {window_id} not found")
            return False

        # Record window area
        return self.start_area(
            window_info.x,
            window_info.y,
            window_info.width,
            window_info.height,
            output_file,
            fps,
            include_mic
        )

    def stop(self, timeout: int = 10) -> Tuple[Optional[str], int, float]:
        """Stop recording gracefully.

        Args:
            timeout: Maximum seconds to wait for FFmpeg to finish

        Returns:
            Tuple of (output_file, file_size_bytes, duration_seconds)
            Returns (None, 0, 0) on error
        """
        if self.state != RecordingState.RECORDING:
            logger.warning(f"Cannot stop recording in state: {self.state}")
            return (None, 0, 0)

        self.state = RecordingState.STOPPING

        try:
            # Send SIGINT for graceful shutdown (same as Ctrl+C)
            # This makes FFmpeg finalize the file properly
            if self.process:
                import signal
                self.process.send_signal(signal.SIGINT)

            # Wait for FFmpeg to finish
            self.process.wait(timeout=timeout)

            # Calculate stats
            duration = time.time() - self.start_time if self.start_time else 0
            file_size = 0

            if self.output_file and os.path.exists(self.output_file):
                file_size = os.path.getsize(self.output_file)
                logger.info(f"Recording stopped: {duration:.1f}s, {file_size} bytes")
            else:
                logger.warning("Output file not found after recording")

            self.state = RecordingState.STOPPED
            return (self.output_file, file_size, duration)

        except subprocess.TimeoutExpired:
            logger.warning(f"FFmpeg did not stop gracefully, force killing")
            self.abort()
            return (None, 0, 0)

        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            self.state = RecordingState.ERROR
            return (None, 0, 0)

    def abort(self):
        """Abort recording immediately and delete output file."""
        if self.process:
            try:
                self.process.kill()
                self.process.wait(timeout=2)
            except Exception as e:
                logger.error(f"Error killing FFmpeg process: {e}")

        # Delete output file
        if self.output_file and os.path.exists(self.output_file):
            try:
                os.remove(self.output_file)
                logger.info(f"Deleted recording file: {self.output_file}")
            except Exception as e:
                logger.error(f"Error deleting file: {e}")

        self.state = RecordingState.STOPPED

    def get_file_size(self) -> int:
        """Get current recording file size.

        Returns:
            File size in bytes, 0 if file doesn't exist
        """
        if self.output_file and os.path.exists(self.output_file):
            try:
                return os.path.getsize(self.output_file)
            except Exception:
                return 0
        return 0

    def get_duration(self) -> float:
        """Get current recording duration.

        Returns:
            Duration in seconds, 0 if not recording
        """
        if self.state == RecordingState.RECORDING and self.start_time:
            return time.time() - self.start_time
        return 0.0

    def _build_ffmpeg_command(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        output_file: str,
        fps: int,
        include_mic: bool
    ) -> list:
        """Build FFmpeg command for x11grab recording.

        Args:
            x, y: Capture offset
            width, height: Capture dimensions
            output_file: Output file path
            fps: Frame rate
            include_mic: Include microphone

        Returns:
            FFmpeg command as list
        """
        # Video input
        cmd = [
            'ffmpeg', '-y',
            '-video_size', f'{width}x{height}',
            '-framerate', str(fps),
            '-f', 'x11grab',
            '-i', f':0.0+{x},{y}',
        ]

        # Audio input
        audio_args = self.audio_system.build_ffmpeg_audio_args(include_mic)
        cmd.extend(audio_args)

        # Video encoding
        if self._hw_encoder == 'h264_nvenc':
            cmd.extend(['-c:v', 'h264_nvenc'])
        elif self._hw_encoder == 'h264_vaapi':
            cmd.extend(['-vaapi_device', '/dev/dri/renderD128', '-c:v', 'h264_vaapi'])
        else:
            cmd.extend(['-c:v', 'libx264', '-preset', 'ultrafast'])

        # Output
        cmd.append(output_file)

        logger.debug(f"FFmpeg command: {' '.join(cmd)}")
        return cmd

    def _read_stderr(self):
        """Read FFmpeg stderr output in background thread."""
        try:
            if self.process and self.process.stderr:
                for line in self.process.stderr:
                    decoded = line.decode('utf-8', errors='replace').strip()
                    self._stderr_output += decoded + "\n"
                    # Check for error indicators
                    if 'Error' in decoded or 'failed' in decoded.lower():
                        self._process_error = decoded
                        logger.error(f"FFmpeg error: {decoded}")
        except Exception as e:
            logger.debug(f"Stderr reader ended: {e}")

    def is_process_alive(self) -> bool:
        """Check if FFmpeg process is still running.

        Returns:
            True if process is running, False if it has exited
        """
        if self.process is None:
            return False
        return self.process.poll() is None

    def get_error(self) -> Optional[str]:
        """Get FFmpeg error message if process failed.

        Returns:
            Error message string if process failed, None if running normally
        """
        if self.state != RecordingState.RECORDING:
            return None

        # Check if process died unexpectedly
        if self.process and self.process.poll() is not None:
            # Process has exited
            if self._process_error:
                return self._process_error
            # Try to extract error from stderr
            if self._stderr_output:
                # Look for common error patterns
                for line in reversed(self._stderr_output.split('\n')):
                    if 'Error' in line or 'failed' in line.lower() or 'No capable devices' in line:
                        return line.strip()
                # Return last non-empty line as fallback
                for line in reversed(self._stderr_output.split('\n')):
                    if line.strip():
                        return line.strip()
            return "FFmpeg process exited unexpectedly"
        return None


class XCompositeRecorder(FFmpegRecorder):
    """XComposite-based window tracker for video recording.

    Captures window content using XComposite and tracks window movement.
    Window content is piped to FFmpeg as raw video frames.
    """

    def __init__(self):
        super().__init__()
        self.window_id: Optional[int] = None
        self.capture_thread: Optional[threading.Thread] = None
        self.stop_flag = threading.Event()

    def start_window_tracking(
        self,
        window_id: int,
        output_file: str,
        fps: int = 30,
        include_mic: bool = False
    ) -> bool:
        """Start recording window with movement tracking.

        The recording follows the window as it moves across the screen.

        Args:
            window_id: X11 window ID to record
            output_file: Path to output video file
            fps: Frames per second
            include_mic: Include microphone input

        Returns:
            True if recording started successfully
        """
        if self.state != RecordingState.IDLE:
            logger.error(f"Cannot start recording in state: {self.state}")
            return False

        # Get window info
        window_detector = WindowDetector()
        windows = window_detector.get_visible_windows()

        window_info = None
        for win in windows:
            if win.window_id == window_id:
                window_info = win
                break

        if not window_info:
            logger.error(f"Window {window_id} not found")
            return False

        # Ensure even dimensions
        width = window_info.width - (window_info.width % 2)
        height = window_info.height - (window_info.height % 2)

        # Redirect window to XComposite off-screen buffer
        try:
            self.capture.xcomposite.redirect_window(window_id)
        except Exception as e:
            logger.error(f"Failed to redirect window to XComposite: {e}")
            return False

        # Build FFmpeg command for raw video input
        cmd = self._build_rawvideo_ffmpeg_command(width, height, output_file, fps, include_mic)

        try:
            # Start FFmpeg with stdin for raw frames and stderr capture
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )

            self.window_id = window_id
            self.output_file = output_file
            self.recording_area = (0, 0, width, height)  # Area is dynamic
            self.start_time = time.time()
            self.state = RecordingState.RECORDING
            self.stop_flag.clear()
            self._stderr_output = ""
            self._process_error = None

            # Start stderr reader thread
            self._stderr_thread = threading.Thread(
                target=self._read_stderr,
                daemon=True
            )
            self._stderr_thread.start()

            # Start frame capture thread
            self.capture_thread = threading.Thread(
                target=self._capture_loop,
                args=(window_id, width, height, fps),
                daemon=True
            )
            self.capture_thread.start()

            logger.info(f"Started XComposite recording: window {window_id} -> {output_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to start XComposite recording: {e}")
            self.state = RecordingState.ERROR
            return False

    def stop(self, timeout: int = 10) -> Tuple[Optional[str], int, float]:
        """Stop XComposite recording gracefully.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            Tuple of (output_file, file_size_bytes, duration_seconds)
        """
        if self.state != RecordingState.RECORDING:
            return (None, 0, 0)

        self.state = RecordingState.STOPPING
        self.stop_flag.set()

        # Wait for capture thread to finish
        if self.capture_thread:
            self.capture_thread.join(timeout=2)

        # Close FFmpeg stdin to signal end of input
        if self.process and self.process.stdin:
            try:
                self.process.stdin.close()
            except Exception:
                pass

        # Wait for FFmpeg to finish encoding
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg did not finish, force killing")
            self.process.kill()

        # Calculate stats
        duration = time.time() - self.start_time if self.start_time else 0
        file_size = self.get_file_size()

        self.state = RecordingState.STOPPED
        logger.info(f"XComposite recording stopped: {duration:.1f}s, {file_size} bytes")

        return (self.output_file, file_size, duration)

    def _capture_loop(self, window_id: int, width: int, height: int, fps: int):
        """Frame capture loop (runs in separate thread).

        Args:
            window_id: Window to capture
            width, height: Frame dimensions
            fps: Target frame rate
        """
        frame_time = 1.0 / fps
        last_frame_time = time.time()

        logger.info(f"Starting frame capture loop at {fps} FPS")

        while not self.stop_flag.is_set():
            try:
                frame_start = time.time()

                # Capture frame from XComposite
                frame_data = self.capture.xcomposite.capture_frame_raw(
                    window_id,
                    width,
                    height
                )

                if frame_data is None:
                    logger.warning("Failed to capture frame, using blank frame")
                    # Send blank frame to maintain timing
                    frame_data = bytes(width * height * 3)

                # Write to FFmpeg stdin
                try:
                    self.process.stdin.write(frame_data)
                    self.process.stdin.flush()
                except (BrokenPipeError, AttributeError):
                    logger.warning("FFmpeg stdin closed, stopping capture")
                    break

                # Frame timing
                elapsed = time.time() - frame_start
                sleep_time = max(0, frame_time - elapsed)
                time.sleep(sleep_time)

                # Log performance
                actual_fps = 1.0 / (time.time() - last_frame_time) if last_frame_time else 0
                if actual_fps < fps * 0.8:  # Warn if < 80% of target FPS
                    logger.warning(f"Frame capture slow: {actual_fps:.1f} FPS (target: {fps})")

                last_frame_time = time.time()

            except Exception as e:
                logger.error(f"Error in capture loop: {e}")
                break

        logger.info("Frame capture loop ended")

    def _build_rawvideo_ffmpeg_command(
        self,
        width: int,
        height: int,
        output_file: str,
        fps: int,
        include_mic: bool
    ) -> list:
        """Build FFmpeg command for raw video stdin input.

        Args:
            width, height: Video dimensions
            output_file: Output file path
            fps: Frame rate
            include_mic: Include microphone

        Returns:
            FFmpeg command as list
        """
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output file

            # Raw video input from stdin
            '-f', 'rawvideo',
            '-pix_fmt', 'bgr24',  # XGetImage returns BGR
            '-s', f'{width}x{height}',
            '-r', str(fps),
            '-i', '-',  # Read from stdin
        ]

        # Audio input
        audio_args = self.audio_system.build_ffmpeg_audio_args(include_mic)
        cmd.extend(audio_args)

        # Video encoding
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
        ])

        # Output container
        cmd.extend([
            '-f', 'matroska',
            output_file
        ])

        logger.debug(f"FFmpeg rawvideo command: {' '.join(cmd)}")
        return cmd
