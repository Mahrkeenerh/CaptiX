"""Audio system detection for video recording.

Detects available audio sources (PulseAudio/PipeWire) and builds
FFmpeg audio arguments for screen recording.
"""

import subprocess
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class AudioSystem:
    """Detect and configure audio sources for video recording."""

    def __init__(self):
        self.backend = self._detect_backend()
        self.system_audio = None
        self.microphone = None

        if self.backend:
            self.system_audio = self._get_system_audio_source()
            self.microphone = self._get_microphone_source()

    def _detect_backend(self) -> Optional[str]:
        """Detect audio backend (PulseAudio or PipeWire).

        Returns:
            'pulse' if PulseAudio/PipeWire detected, None otherwise
        """
        try:
            result = subprocess.run(
                ['pactl', '--version'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                output = result.stdout.lower()
                if 'pipewire' in output:
                    logger.info("Detected PipeWire audio backend")
                    return 'pulse'  # PipeWire uses PulseAudio protocol
                elif 'pulseaudio' in output or 'libpulse' in output:
                    logger.info("Detected PulseAudio backend")
                    return 'pulse'

            logger.warning("No PulseAudio/PipeWire backend detected")
            return None

        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("pactl not found - no audio will be recorded")
            return None

    def _get_system_audio_source(self) -> Optional[str]:
        """Get default system audio sink monitor.

        Returns:
            Source name or 'default' if available, None otherwise
        """
        if not self.backend:
            return None

        try:
            # Try to get default sink monitor
            result = subprocess.run(
                ['pactl', 'list', 'short', 'sinks'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0 and result.stdout:
                # Use default monitor
                logger.info("System audio source available")
                return 'default'

            return None

        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Failed to detect system audio source")
            return None

    def _get_microphone_source(self) -> Optional[str]:
        """Get default microphone input source.

        Returns:
            Source name if available, None otherwise
        """
        if not self.backend:
            return None

        try:
            # Check for input sources
            result = subprocess.run(
                ['pactl', 'list', 'short', 'sources'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0 and result.stdout:
                # Look for input devices (not monitors)
                for line in result.stdout.split('\n'):
                    if line and '.monitor' not in line:
                        logger.info("Microphone source available")
                        return '@DEFAULT_SOURCE@'

            logger.info("No microphone source detected")
            return None

        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Failed to detect microphone source")
            return None

    def build_ffmpeg_audio_args(self, include_microphone: bool = False) -> List[str]:
        """Build FFmpeg audio input arguments.

        Args:
            include_microphone: Whether to include microphone input

        Returns:
            List of FFmpeg arguments for audio input, empty if no audio
        """
        if not self.backend or not self.system_audio:
            logger.warning("No audio backend available - video will have no audio")
            return []

        args = []

        if include_microphone and self.microphone:
            # System audio + microphone with mixing
            args.extend([
                '-f', 'alsa', '-i', 'default',
                '-f', 'alsa', '-i', self.microphone,
                '-filter_complex', '[1:a][2:a]amix=inputs=2:duration=first[a]',
                '-map', '0:v', '-map', '[a]',
            ])
        else:
            # System audio only (ALSA for PipeWire compatibility)
            args.extend(['-f', 'alsa', '-i', 'default'])

        args.extend(['-c:a', 'aac'])

        return args

    def get_audio_info(self) -> str:
        """Get human-readable audio configuration info.

        Returns:
            Description of audio setup
        """
        if not self.backend:
            return "No audio"

        if self.system_audio and self.microphone:
            return "System + Mic"
        elif self.system_audio:
            return "System audio"
        else:
            return "No audio"


def get_audio_system() -> AudioSystem:
    """Get global AudioSystem instance.

    Returns:
        AudioSystem instance
    """
    return AudioSystem()
