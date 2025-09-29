#!/usr/bin/env python3
"""
CaptiX - Fast screenshot and screen recording tool for Linux X11

Main entry point and CLI interface.
Phase 1: Basic screenshot functionality with command-line interface.
"""

import argparse
import sys
import os
from pathlib import Path


def setup_directories():
    """Ensure default directories exist."""
    screenshots_dir = os.path.expanduser("~/Pictures/Screenshots")
    videos_dir = os.path.expanduser("~/Videos/Recordings")
    
    Path(screenshots_dir).mkdir(parents=True, exist_ok=True)
    Path(videos_dir).mkdir(parents=True, exist_ok=True)
    
    return screenshots_dir, videos_dir


def cmd_screenshot(args):
    """Handle screenshot command."""
    # Import here to avoid issues with path setup
    from utils.capture import capture_screenshot
    
    print("Taking screenshot...")
    
    try:
        if args.area:
            # Parse area format: "x,y,width,height"
            try:
                x, y, width, height = map(int, args.area.split(','))
                filepath, size = capture_screenshot(x, y, width, height, 
                                                  save_path=args.output, 
                                                  include_cursor=not args.no_cursor)
            except ValueError:
                print("Error: Area format should be 'x,y,width,height' (e.g., '100,100,800,600')")
                return 1
        else:
            # Full screen capture
            filepath, size = capture_screenshot(save_path=args.output, 
                                              include_cursor=not args.no_cursor)
        
        print(f"Screenshot saved: {filepath}")
        print(f"File size: {size} bytes ({size/1024:.1f} KB)")
        return 0
        
    except Exception as e:
        print(f"Error taking screenshot: {e}")
        return 1


def cmd_info(args):
    """Display system information."""
    from utils.capture import ScreenCapture
    
    capture = ScreenCapture()
    try:
        x, y, width, height = capture.get_screen_geometry()
        print(f"Screen geometry: {width}x{height} at ({x}, {y})")
        
        # Display information about the capture system
        print(f"X11 Display: {capture.display.get_display_name()}")
        print(f"Screen depth: {capture.screen.root_depth}")
        
    except Exception as e:
        print(f"Error getting system info: {e}")
        return 1
    finally:
        capture.cleanup()
    
    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="CaptiX - Fast screenshot and screen recording tool for Linux X11",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --screenshot                    # Take full screen screenshot
  %(prog)s --screenshot --area 100,100,800,600  # Capture specific area  
  %(prog)s --screenshot --no-cursor       # Screenshot without cursor
  %(prog)s --screenshot --output /tmp/    # Save to custom directory
  %(prog)s --info                         # Show system information
        """
    )
    
    # Commands
    parser.add_argument('--screenshot', action='store_true',
                       help='Take a screenshot')
    parser.add_argument('--info', action='store_true',
                       help='Show system information')
    
    # Screenshot options
    parser.add_argument('--area', metavar='x,y,w,h',
                       help='Capture specific area (format: x,y,width,height)')
    parser.add_argument('--no-cursor', action='store_true',
                       help='Exclude cursor from screenshot')
    parser.add_argument('--output', '-o', metavar='PATH',
                       help='Output directory or file path')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Ensure directories exist
    setup_directories()
    
    # Execute commands
    if args.screenshot:
        return cmd_screenshot(args)
    elif args.info:
        return cmd_info(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())