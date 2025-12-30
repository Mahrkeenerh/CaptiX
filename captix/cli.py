#!/usr/bin/env python3
"""
CaptiX CLI interface and command routing.

This module handles command-line argument parsing and routes commands
to appropriate handlers (screenshot, UI, system info, window management).

Main entry point: captix/__main__.py or captix-screenshot wrapper script.
"""

import argparse
import sys
import os
from pathlib import Path
from captix.utils.paths import CaptiXPaths


def setup_directories():
    return CaptiXPaths.ensure_directories()


def cmd_screenshot(args) -> int:
    """Handle screenshot command."""
    # Import here to avoid issues with path setup
    from captix.utils.capture import (
        capture_screenshot,
        capture_window_at_position,
        capture_window_at_position_pure,
    )

    print("Taking screenshot...")

    try:
        if args.window_pure_at:
            # Capture pure window content at specific coordinates
            try:
                x, y = map(int, args.window_pure_at.split(","))
                filepath, size = capture_window_at_position_pure(
                    x,
                    y,
                    save_path=args.output,
                    include_cursor=not args.no_cursor,
                    copy_to_clipboard=not args.no_clipboard,
                )
                print("Pure window content captured (no overlaps)")
            except ValueError:
                print("Error: Window position format should be 'x,y' (e.g., '500,300')")
                return 1
        elif args.window_at:
            # Capture window at specific coordinates
            try:
                x, y = map(int, args.window_at.split(","))
                filepath, size = capture_window_at_position(
                    x,
                    y,
                    save_path=args.output,
                    include_cursor=not args.no_cursor,
                    copy_to_clipboard=not args.no_clipboard,
                )
            except ValueError:
                print("Error: Window position format should be 'x,y' (e.g., '500,300')")
                return 1
        elif args.area:
            # Parse area format: "x,y,width,height"
            try:
                x, y, width, height = map(int, args.area.split(','))
                filepath, size = capture_screenshot(
                    x,
                    y,
                    width,
                    height,
                    save_path=args.output,
                    include_cursor=not args.no_cursor,
                    copy_to_clipboard=not args.no_clipboard,
                )
            except ValueError:
                print("Error: Area format should be 'x,y,width,height' (e.g., '100,100,800,600')")
                return 1
        else:
            # Full screen capture
            filepath, size = capture_screenshot(
                save_path=args.output,
                include_cursor=not args.no_cursor,
                copy_to_clipboard=not args.no_clipboard,
            )

        print(f"Screenshot saved: {filepath}")
        print(f"File size: {size} bytes ({size/1024:.1f} KB)")

        # Inform user about clipboard
        if not args.no_clipboard:
            print("Screenshot copied to clipboard")

        return 0

    except Exception as e:
        print(f"Error taking screenshot: {e}")
        return 1


def cmd_video_ui(args) -> int:
    """Handle video recording with interactive UI."""
    import subprocess
    from PyQt6.QtWidgets import QApplication
    from captix.ui import ScreenshotOverlay
    from captix.utils.video_recorder import FFmpegRecorder
    from captix.utils.recording_panel import RecordingControlPanel, RecordingAreaBorder
    from captix.utils.notifications import notify_recording_saved
    from captix.utils.paths import CaptiXPaths
    from captix.utils.recording_service import is_recording_active, stop_active_recording, VideoRecordingService
    from datetime import datetime

    # Check if recording is already active
    if is_recording_active():
        print("Recording is active - stopping it...")
        if stop_active_recording():
            print("Stop command sent successfully")
            return 0
        else:
            print("Failed to stop recording")
            return 1

    print("Launching video recording selection UI...")

    app = QApplication(sys.argv)

    # CRITICAL: Don't quit when overlay closes - we need to show the recording panel!
    app.setQuitOnLastWindowClosed(False)

    # Create overlay in video mode
    overlay = ScreenshotOverlay(video_mode=True)

    # Storage for recorder and control panel (include overlay for cleanup)
    active_recorder = {'recorder': None, 'panel': None, 'border': None, 'service': None, 'overlay': overlay}

    def start_recording(x, y, width, height, is_fullscreen, window_id, track_window):
        """Start recording after area selection."""
        print(f"start_recording called: {width}x{height} at ({x},{y}), fullscreen={is_fullscreen}, window_id={window_id}, track={track_window}")
        try:
            # Determine capture type suffix (same convention as screenshots)
            if is_fullscreen:
                capture_type = "full"
            elif window_id:
                capture_type = "win"
            else:
                capture_type = "area"

            # Generate output filename with type suffix (use month-based subfolder)
            videos_dir = Path(CaptiXPaths.get_videos_month_dir())
            videos_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            output_file = str(videos_dir / f"rec_{timestamp}_{capture_type}.mkv")

            # Use FFmpeg x11grab for all recording types (static area)
            # Note: XComposite window tracking is disabled because it conflicts with
            # modern desktop compositors (BadAccess error on XCompositeRedirectWindow)
            print(f"Starting area recording: {width}x{height} at ({x},{y})...")
            recorder = FFmpegRecorder()
            success = recorder.start_area(
                x, y, width, height,
                output_file,
                fps=30,
                include_mic=False
            )

            if not success:
                print("Failed to start recording")
                # Show error notification to user
                try:
                    subprocess.run([
                        'notify-send',
                        '-u', 'critical',
                        '-i', 'error',
                        'CaptiX Recording Failed',
                        'Failed to start video recording. Check if FFmpeg is installed.'
                    ])
                except:
                    pass
                app.quit()
                return

            # Create control panel
            panel = RecordingControlPanel(
                recorder,
                (x, y, width, height),
                is_fullscreen
            )

            # Create border (if not fullscreen)
            border = None
            if not is_fullscreen:
                border = RecordingAreaBorder(x, y, width, height)
                border.show()

            # Define stop/abort handlers
            def on_stop():
                print("Stopping recording...")

                # Release D-Bus service
                if active_recorder['service']:
                    active_recorder['service'].release()

                # Hide UI immediately (before waiting for recording to finish)
                try:
                    if active_recorder['overlay']:
                        active_recorder['overlay'].close()
                except RuntimeError:
                    pass  # Already deleted
                if border:
                    border.close()
                panel.close()
                app.processEvents()  # Ensure UI updates immediately

                # Now stop recording (this may take time to finalize the video)
                final_path, file_size, duration = recorder.stop()

                if final_path:
                    print(f"Recording saved: {final_path}")
                    print(f"Duration: {duration:.1f}s, Size: {file_size} bytes")

                    # Format duration for notification (MM:SS)
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    duration_str = f"{minutes}:{seconds:02d}"

                    # Show notification with sound (after recording is fully saved)
                    try:
                        notify_recording_saved(final_path, file_size, duration_str)
                    except Exception as e:
                        print(f"Warning: Failed to show notification: {e}")

                app.quit()

            def on_abort():
                print("Aborting recording...")

                # Release D-Bus service
                if active_recorder['service']:
                    active_recorder['service'].release()

                recorder.abort()

                # Cleanup
                try:
                    if active_recorder['overlay']:
                        active_recorder['overlay'].close()
                except RuntimeError:
                    pass  # Already deleted
                if border:
                    border.close()
                panel.close()
                app.quit()

            panel.stop_requested.connect(on_stop)
            panel.abort_requested.connect(on_abort)

            # Register D-Bus service for remote control (after on_stop is defined)
            try:
                recording_service = VideoRecordingService(on_stop)
                active_recorder['service'] = recording_service
                print("Recording service registered - hotkey will now stop the recording")
            except Exception as e:
                print(f"Warning: Failed to register recording service: {e}")
                print("Recording will work but hotkey won't stop it")

            panel.show()

            # Store references
            active_recorder['recorder'] = recorder
            active_recorder['panel'] = panel
            active_recorder['border'] = border

        except Exception as e:
            print(f"Error starting recording: {e}")
            import traceback
            traceback.print_exc()
            # Show error notification to user
            try:
                subprocess.run([
                    'notify-send',
                    '-u', 'critical',
                    '-i', 'error',
                    'CaptiX Recording Error',
                    f'Error starting recording: {str(e)}'
                ])
            except:
                pass
            app.quit()

    # Connect selection signal
    overlay.recording_area_selected.connect(start_recording)

    # Show overlay
    overlay.showFullScreen()

    return app.exec()


def cmd_info(args) -> int:
    """Display system information."""
    from captix.utils.capture import ScreenCapture

    capture = ScreenCapture()
    try:
        x, y, width, height = capture.get_screen_geometry()
        print(f"Screen geometry: {width}x{height} at ({x}, {y})")

        # Display information about the capture system
        print(f"X11 Display: {capture.display.get_display_name()}")
        print(f"Screen depth: {capture.screen.root_depth}")

        # Show window detection capability
        if capture.window_detector:
            print("Window detection: Available")
        else:
            print("Window detection: Not available")

    except Exception as e:
        print(f"Error getting system info: {e}")
        return 1
    finally:
        capture.cleanup()

    return 0


def cmd_list_windows(args) -> int:
    """List all visible windows."""
    from captix.utils.capture import list_visible_windows

    print("Listing visible windows...")

    try:
        windows = list_visible_windows()

        if not windows:
            print("No visible windows found.")
            return 0

        print(f"\nFound {len(windows)} visible windows:")
        print("-" * 80)
        print(f"{'ID':<12} {'Class':<20} {'Title':<30} {'Geometry':<15}")
        print("-" * 80)

        for window in windows:
            # Truncate long titles and class names for display
            class_name = (
                window.class_name[:19]
                if len(window.class_name) > 19
                else window.class_name
            )
            title = window.title[:29] if len(window.title) > 29 else window.title
            geometry = f"{window.width}x{window.height}"

            print(f"{window.window_id:<12} {class_name:<20} {title:<30} {geometry:<15}")

        return 0

    except Exception as e:
        print(f"Error listing windows: {e}")
        return 1


def cmd_window_info(args) -> int:
    """Get information about window at specific coordinates."""
    from captix.utils.capture import get_window_info_at_position

    try:
        x, y = map(int, args.position.split(","))
    except ValueError:
        print("Error: Position format should be 'x,y' (e.g., '500,300')")
        return 1

    print(f"Getting window information at position ({x}, {y})...")

    try:
        window_info = get_window_info_at_position(x, y)

        if not window_info:
            print("No window found at specified position.")
            return 1

        print("\nWindow Information:")
        print(f"  ID: {window_info.window_id}")
        print(f"  Class: {window_info.class_name}")
        print(f"  Title: {window_info.title}")
        print(f"  Position: ({window_info.x}, {window_info.y})")
        print(f"  Size: {window_info.width}x{window_info.height}")
        print(f"  Is Root/Desktop: {window_info.is_root}")

        return 0

    except Exception as e:
        print(f"Error getting window info: {e}")
        return 1


def cmd_test_clipboard(args) -> int:
    """Test clipboard functionality."""
    from captix.utils.clipboard import test_clipboard_availability

    print("Testing clipboard availability...")

    try:
        if test_clipboard_availability():
            print("✅ Clipboard is available and working")
            return 0
        else:
            print("❌ Clipboard is not available")
            return 1
    except Exception as e:
        print(f"❌ Clipboard test failed: {e}")
        return 1


def cmd_screenshot_ui(args) -> int:
    """Launch interactive screenshot UI."""
    try:
        from captix.ui import main as screenshot_ui_main

        print("Launching interactive screenshot UI...")
        return screenshot_ui_main()
    except ImportError as e:
        print(f"❌ Failed to import screenshot UI: {e}")
        print("Make sure PyQt6 is installed: pip install PyQt6")
        return 1
    except Exception as e:
        print(f"❌ Error launching screenshot UI: {e}")
        return 1


def main() -> int:
    """Main entry point for CLI interface."""
    parser = argparse.ArgumentParser(
        description="CaptiX - Fast screenshot and screen recording tool for Linux X11",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --screenshot                           # Take full screen screenshot
  %(prog)s --screenshot --area 100,100,800,600   # Capture specific area
  %(prog)s --screenshot --window-at 500,300      # Capture window at coordinates
  %(prog)s --screenshot --window-pure-at 500,300 # Capture pure window content (no overlaps)
  %(prog)s --screenshot --no-cursor              # Screenshot without cursor
  %(prog)s --screenshot --no-clipboard           # Screenshot without clipboard copy
  %(prog)s --screenshot --output /tmp/           # Save to custom directory
  %(prog)s --ui                                  # Launch interactive screenshot UI
  %(prog)s --info                                # Show system information
  %(prog)s --list-windows                        # List all visible windows
  %(prog)s --window-info 500,300                 # Get window info at coordinates
        """,
    )

    # Commands
    parser.add_argument('--screenshot', action='store_true',
                       help='Take a screenshot')
    parser.add_argument(
        "--ui", action="store_true", help="Launch interactive screenshot UI"
    )
    parser.add_argument(
        "--video", action="store_true", help="Launch interactive video recording UI"
    )
    parser.add_argument('--info', action='store_true',
                       help='Show system information')
    parser.add_argument(
        "--list-windows", action="store_true", help="List all visible windows"
    )
    parser.add_argument(
        "--window-info",
        metavar="x,y",
        dest="position",
        help="Get information about window at coordinates (format: x,y)",
    )
    parser.add_argument(
        "--test-clipboard", action="store_true", help="Test clipboard functionality"
    )

    # Screenshot options
    parser.add_argument('--area', metavar='x,y,w,h',
                       help='Capture specific area (format: x,y,width,height)')
    parser.add_argument(
        "--window-at", metavar="x,y", help="Capture window at coordinates (format: x,y)"
    )
    parser.add_argument(
        "--window-pure-at",
        metavar="x,y",
        help="Capture pure window content at coordinates - no overlaps (format: x,y)",
    )
    parser.add_argument('--no-cursor', action='store_true',
                       help='Exclude cursor from screenshot')
    parser.add_argument(
        "--no-clipboard",
        action="store_true",
        help="Do not copy screenshot to clipboard",
    )
    parser.add_argument('--output', '-o', metavar='PATH',
                       help='Output directory or file path')

    # Parse arguments
    args = parser.parse_args()

    # Ensure directories exist
    setup_directories()

    # Execute commands
    if args.screenshot:
        return cmd_screenshot(args)
    elif args.ui:
        return cmd_screenshot_ui(args)
    elif args.video:
        return cmd_video_ui(args)
    elif args.info:
        return cmd_info(args)
    elif args.list_windows:
        return cmd_list_windows(args)
    elif args.position:  # --window-info
        return cmd_window_info(args)
    elif args.test_clipboard:
        return cmd_test_clipboard(args)
    else:
        parser.print_help()
        return 0
